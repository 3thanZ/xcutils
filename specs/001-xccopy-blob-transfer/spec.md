# Feature Specification: xccopy — cross-cloud blob copy

**Feature Branch**: `001-xccopy-blob-transfer`

**Created**: 2026-06-18

**Status**: Draft

**Input**: User description: "create a specification for the xccopy utility. The following are the functional requirements: xccopy from one blob storage location to another; xccopy should allow parallel streaming of blocks to speed up transfer, by default use 3 parallel streams but allow the user to override that; xccopy should allow for resumable transfers."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Copy an object between clouds (Priority: P1)

A user wants to move a single stored object from one cloud's blob storage to another
cloud's blob storage (e.g. from Google Cloud Storage to Azure Blob Storage). They have
already signed in to both cloud CLIs. They run one command naming the source and the
destination, and the object appears at the destination, byte-for-byte identical. The
object streams through the host running xccopy directly from source to destination — the
host never assembles or stores the whole object — so even very large objects can be moved
from a host with limited storage.

**Why this priority**: This is the core purpose of the utility. Without it, nothing
else matters. It is a complete, demonstrable product on its own.

**Independent Test**: Sign in to both clouds, run xccopy with a source and destination
URI for a modestly sized object, and confirm the destination object exists and its
contents match the source.

**Acceptance Scenarios**:

1. **Given** the user is signed in to both the source and destination cloud CLIs and the source object exists, **When** they run xccopy with valid source and destination URIs, **Then** the object is copied to the destination and its contents match the source exactly.
2. **Given** the source and destination are in the same cloud, **When** the user runs xccopy, **Then** the object is copied successfully.
3. **Given** the destination already contains an object at that location, **When** the user runs xccopy without requesting resume, **Then** the destination object is overwritten with the source object.
4. **Given** the user is not signed in to a required cloud CLI, **When** they run xccopy, **Then** the command fails immediately with a message stating exactly which sign-in command to run, and no partial object is left at the destination.
5. **Given** the host running xccopy has far less free storage than the size of the source object, **When** the user copies that object, **Then** the transfer completes successfully without ever storing the whole object on the host.

---

### User Story 2 - Speed up large transfers with parallel streaming (Priority: P2)

A user copying a large object wants the transfer to complete faster by moving multiple
blocks of the object concurrently. By default the utility uses 3 parallel streams, and
the user can raise or lower that number to suit their bandwidth and the object size.

**Why this priority**: Large objects are the common migration case; parallelism makes
the tool practical at scale. It builds on P1 but P1 is usable without it.

**Independent Test**: Copy a large object with the default concurrency and again with a
higher concurrency, and confirm the transfer completes correctly in both cases and is
faster at higher concurrency for a sufficiently large object.

**Acceptance Scenarios**:

1. **Given** a large source object, **When** the user runs xccopy without specifying concurrency, **Then** the transfer uses 3 parallel streams and completes with a correct copy.
2. **Given** a large source object, **When** the user overrides concurrency to a higher value, **Then** the transfer uses that number of parallel streams and produces a correct copy.
3. **Given** the user supplies an invalid concurrency (zero, negative, or non-numeric), **When** they run xccopy, **Then** the command rejects the input with a clear error before transferring anything.

---

### User Story 3 - Resume an interrupted transfer (Priority: P3)

A user's large transfer is interrupted (network drop, machine sleep, cancellation).
Rather than starting over, they re-run the command with an explicit resume option and
the transfer continues, skipping the blocks that already completed.

**Why this priority**: Resumability saves time and bandwidth on large migrations over
unreliable links, but the tool is still useful without it (re-run from scratch).

**Independent Test**: Begin copying a large object, interrupt it partway, then re-run
with the resume option and confirm the completed blocks are not re-sent and the final
object matches the source.

**Acceptance Scenarios**:

1. **Given** a transfer was interrupted and progress was recorded, **When** the user re-runs the command with the resume option, **Then** previously completed blocks are not transferred again and the transfer continues to completion.
2. **Given** a transfer was interrupted, **When** the user re-runs the command without the resume option, **Then** the transfer starts over from the beginning and overwrites any partial result.
3. **Given** the user requests resume but the source object has changed since the interrupted run, **When** they run xccopy, **Then** the command refuses to merge inconsistent data and reports the situation rather than producing a corrupt object.
4. **Given** the user requests resume but no recorded progress exists for that source/destination pair, **When** they run xccopy, **Then** the command performs a normal full transfer.

---

### User Story 4 - See copy progress (Priority: P2)

A user running a long transfer wants ongoing feedback that it is working and how far along
it is, rather than a silent command that only reports at the very end.

**Why this priority**: Visible progress is essential UX for long-running migrations;
without it a user cannot tell a slow transfer from a stuck one. It enhances every other
story but they remain testable without it.

**Independent Test**: Start a copy of a sufficiently large object and observe that progress
updates (amount transferred and a completion indication) appear during the transfer and
reach 100% on success.

**Acceptance Scenarios**:

1. **Given** a transfer is in progress, **When** the user watches the command, **Then** they see progress updating over time, including the amount transferred and an indication of overall completion (such as percentage complete and current throughput).
2. **Given** a transfer completes successfully, **When** it finishes, **Then** the progress indication reaches 100% and a success result is reported.
3. **Given** a transfer is resumed, **When** it runs, **Then** the displayed progress accounts for the already-completed portion rather than restarting from zero.

---

### Edge Cases

- **Source missing**: source object does not exist → clear error, non-zero exit, nothing written.
- **Destination not writable**: destination container/bucket missing or no write permission → clear error before/while transferring.
- **Expired session**: a CLI session exists but has expired → treated like missing auth, with the re-authentication command shown.
- **Zero-byte object**: an empty source object is copied as a valid empty destination object.
- **Mid-transfer interruption**: the destination is never left looking like a complete, valid object when the transfer did not finish.
- **Source changes during transfer**: detected via the source's identity (size/version), preventing a silently corrupt copy.
- **Excessive concurrency**: very large concurrency values are accepted only up to a sane bound, or clearly rejected, rather than exhausting resources.
- **Host storage smaller than object**: the host running xccopy has less free disk/memory than the object size → the transfer still succeeds because the whole object is never stored on the host.
- **Transient buffer cleanup**: if the transfer fails or is aborted mid-flight, in-flight block buffers on the host are released and no source object data is left behind on the host.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The utility MUST copy a single object from a user-specified source location to a user-specified destination location.
- **FR-002**: The utility MUST support source and destination in different clouds (cross-cloud) as well as both in the same cloud.
- **FR-003**: The utility MUST authenticate solely by reusing the user's existing cloud CLI sessions and MUST NOT accept, store, or log service account keys, connection strings, or credential files.
- **FR-004**: The utility MUST move data in bounded blocks and MUST NOT require loading the entire object into memory or onto local disk.
- **FR-005**: The utility MUST transfer multiple blocks concurrently, defaulting to 3 parallel streams.
- **FR-006**: Users MUST be able to override the number of parallel streams.
- **FR-007**: The utility MUST validate the requested concurrency and reject invalid values (zero, negative, non-numeric, or beyond a safe upper bound) before transferring data.
- **FR-008**: On a normal run (resume not requested), if the destination already exists, the utility MUST overwrite it with a fresh transfer.
- **FR-009**: The utility MUST support resuming an interrupted transfer when the user explicitly requests resume, transferring only the blocks not already completed.
- **FR-010**: Without an explicit resume request, the utility MUST start a fresh transfer from the beginning.
- **FR-011**: The utility MUST record transfer progress durably enough that an interrupted transfer can later be resumed, keyed to the specific source/destination pair.
- **FR-012**: When resume is requested, the utility MUST detect whether the source has changed since the interrupted run and MUST refuse to produce a copy that mixes old and new source data.
- **FR-013**: The utility MUST verify the integrity of the completed object (e.g. by size and/or content checksum) and MUST NOT report success for a partial or corrupted copy.
- **FR-014**: The utility MUST display copy progress to the user while the transfer is running — showing how much has been transferred and an indication of overall completion (such as percentage complete and current throughput) — updating continuously as the copy proceeds, not only at the end.
- **FR-015**: The utility MUST fail fast with an actionable message when a required CLI session is missing or expired, naming the exact command the user should run.
- **FR-016**: The utility MUST give a clear error when the source object is missing or the destination is not writable.
- **FR-017**: On success, the utility MUST finalize the destination object and clear the progress record for that transfer.
- **FR-018**: The utility MUST exit with a zero status on success and a non-zero status on any failure.
- **FR-019**: The utility MUST stream blocks from the source, through the host running xccopy, directly to the destination, and MUST NOT assemble or hold the complete object on the host at any point. *(This pass-through streaming with a small host footprint is the primary goal of the utility.)*
- **FR-020**: The utility MUST NOT persist source block data durably on the host. A block in flight may be held only transiently (in memory or an ephemeral buffer), MUST be bounded in size, and MUST be released once it has been forwarded to the destination — including being cleaned up if the transfer fails or is aborted.
- **FR-021**: The host's local storage and memory footprint MUST remain bounded and independent of the total object size, so that a host with far less free space than the object can still complete the transfer.
- **FR-022**: Any recorded progress/checkpoint data (see FR-011) MUST contain only transfer metadata and MUST NOT contain source object content.

### Key Entities

- **Transfer**: a single copy operation from one source location to one destination location; carries the chosen concurrency and an overall status (in progress, completed, failed).
- **Blob Location**: a pointer to an object in a cloud blob store — the cloud, the bucket/account, the container (where applicable), and the object path.
- **Block**: a bounded portion of the object that is transferred as an independent unit; the granularity at which parallelism and resume operate.
- **Transfer Progress (Checkpoint)**: a durable record of which blocks have completed for a given source/destination pair, plus a fingerprint of the source's identity (e.g. size/version) used to detect source changes on resume.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After signing in to both clouds, a user can copy an object from one cloud to another with a single command and no credential files.
- **SC-002**: For a large object (e.g. 10 GB), copying with the default 3 parallel streams completes meaningfully faster — at least 40% faster — than copying the same object with a single stream.
- **SC-003**: When a transfer interrupted at X% is resumed, the amount of already-completed data re-transferred is no more than one block, and the final object matches the source exactly.
- **SC-004**: Copying a very large object (e.g. 100 GB) uses no more host memory or local storage than copying a small one; the host footprint does not grow with object size.
- **SC-005**: 100% of transfers reported as successful are integrity-verified against the source; no partial or corrupted copy is ever reported as success.
- **SC-006**: When a required cloud session is missing or expired, the user is shown the exact re-authentication command, and the command produces no success output and leaves no partial destination object.
- **SC-007**: A host whose free storage is much smaller than the object (for example, copying a 1 TB object on a host with only a few GB free) can complete the transfer successfully, because at most roughly (number of parallel streams × block size) of object data resides on the host at any moment.
- **SC-008**: During any transfer lasting more than a few seconds, the user sees progress updates at least every few seconds, and the indicated progress reaches 100% exactly when the verified copy completes.

## Assumptions

- **Scope**: exactly one source object to one destination object per invocation. Recursive/prefix copy and whole-bucket migration are out of scope for this version.
- **Supported clouds**: only clouds with an implemented provider — Google Cloud Storage (`gs://`) and Azure Blob Storage (`az://`). AWS S3 (`s3://`) is reserved for a future version.
- **Authentication**: relies on pre-established CLI sessions (`az login`; `gcloud auth application-default login`); the utility never handles long-lived keys. (Per the project constitution.)
- **Resume is opt-in**: resuming requires an explicit resume option; a plain re-run overwrites from scratch.
- **Progress storage**: transfer progress is stored on the machine running xccopy and is keyed to the source/destination pair; it is not shared across machines.
- **Source stability**: the source object is expected to be stable during a transfer; changes are detected on resume via a source fingerprint, not prevented.
- **Connectivity**: the machine running xccopy has network access to both the source and destination clouds.
- **Block size**: a sensible default block size is chosen by the implementation; the user is not required to set it.
- **Pass-through streaming**: data is streamed from source to destination *through* the host running xccopy (not delegated to a server-side or cloud-native copy); the whole object is never assembled on the host. This is the defining goal of xccopy.
- **Transient buffering only**: at most roughly (parallel streams × block size) of object data is held on the host at once — in memory or an ephemeral buffer — and is released as blocks are forwarded; nothing containing object content survives the transfer.
- **Progress output**: progress is shown on the terminal and updates live during the transfer; the recorded checkpoint holds only metadata, never object content.
