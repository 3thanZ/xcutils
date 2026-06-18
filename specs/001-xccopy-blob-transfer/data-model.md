# Phase 1 Data Model: xccopy

Entities are in-process domain objects (and one on-disk JSON record). There is no database.
Field types are described abstractly; see [contracts/](./contracts/) for the concrete
interface and checkpoint-file shapes.

## BlobLocation *(exists)*

A normalized pointer to an object in a cloud blob store. *(Already implemented in
`xcutils_common/uri.py`.)*

| Field | Description |
|-------|-------------|
| `scheme` | `gs`, `az`, or `s3` (s3 reserved) |
| `bucket` | GCS bucket / Azure storage account / S3 bucket |
| `container` | Azure container; `None` for gs/s3 |
| `key` | object path within the container/bucket |

## ObjectStat *(new)*

Result of `stat()` on a source object; basis for block planning, fingerprinting, integrity.

| Field | Description | Validation |
|-------|-------------|------------|
| `size` | total bytes | `>= 0` |
| `fingerprint` | source identity for resume safety — Azure ETag / GCS generation | non-empty for existing objects |
| `content_type` | MIME type to propagate to the destination | optional |
| `source_hash` | server-reported hash (md5/crc32c) if available | optional |

## BlockPlan / Block *(new)*

The deterministic split of the source object into transfer units.

| Field | Description | Validation |
|-------|-------------|------------|
| `block_size` | bytes per block (adaptive; see research D6) | `8 MiB ≤ size ≤ 4000 MiB` |
| `count` | number of blocks = `ceil(size / block_size)` | `≤ 50000` (Azure cap) |
| `Block.index` | 0-based ordinal | `0 ≤ index < count` |
| `Block.offset` | byte offset of the block in the source | `index * block_size` |
| `Block.length` | block byte length | full `block_size`, except possibly the last |
| `Block.block_id` | Azure stage id (derived from index, padded/encoded) | unique per blob |

**State (per block)**: `PENDING → IN_FLIGHT → STAGED → COMMITTED`. Resume re-reads only blocks
not already `STAGED`/`COMMITTED`.

## Transfer *(new)*

A single copy operation for one invocation.

| Field | Description |
|-------|-------------|
| `source` / `destination` | `BlobLocation`s |
| `concurrency` | parallel streams (default 3, `1..32`) |
| `resume` | whether `--resume` was requested |
| `plan` | the `BlockPlan` |
| `status` | overall status (below) |

**State**: `PENDING → RUNNING → VERIFYING → COMPLETED` (or `→ FAILED` from any state).
`VERIFYING` performs the integrity check (FR-013) before reporting success.

## BlockSink *(new — interface; see contracts/provider-interface.md)*

Destination-side abstraction the engine writes blocks into.

| Member | Description |
|--------|-------------|
| `requires_ordered` | `True` if blocks must arrive in index order (GCS); `False` for Azure |
| `already_done()` | set of block indices already persisted (for resume) |
| `stage(block, data)` | persist one block (server-side), with per-block checksum |
| `commit(ordered_indices)` | finalize/assemble the object; returns destination hash/size |
| `abort()` | release engine-side resources; server-side staged state may persist for resume |
| `resume_state()` | serializable metadata for the checkpoint (block-id list / session URI + offset) |

## TransferProgress (Checkpoint) *(new — on-disk JSON, metadata only; FR-011/FR-022)*

One JSON file per transfer (see [contracts/checkpoint-schema.md](./contracts/checkpoint-schema.md)).
Contains **no object bytes and no credentials**.

| Field | Description | Validation |
|-------|-------------|------------|
| `version` | schema version | int |
| `source_uri` / `destination_uri` | identify the transfer | match the request on resume |
| `source_fingerprint` | from `ObjectStat`; gates safe resume (FR-012) | must equal current stat on resume, else refuse |
| `block_size`, `total_size` | block plan inputs | `> 0` (or size 0 special case) |
| `completed_blocks` | indices already staged/committed | subset of `0..count-1` |
| `sink_state` | Azure block-IDs or GCS session URI + offset | sink-specific |
| `created_at` / `updated_at` | timestamps | ISO-8601 |

**Lifecycle**: created on first staged block → updated per completion → **deleted on successful
commit** → cleared at the start of a fresh (non-`--resume`) run.

## ProgressState *(new — transient, in-memory)*

Thread-safe aggregation feeding the live display (FR-014, SC-008).

| Field | Description |
|-------|-------------|
| `total_bytes` | from `ObjectStat.size` |
| `completed_bytes` | atomically incremented as blocks finish; initialized to resumed bytes |
| `started_at` | for throughput/ETA |

## Relationships

```text
Transfer 1──1 BlockPlan 1──* Block
Transfer 1──1 source BlobLocation (read via BlobProvider.read_block)
Transfer 1──1 destination BlobLocation (written via BlockSink from BlobProvider.open_sink)
Transfer 1──1 TransferProgress (checkpoint; persisted/cleared by checkpoint.py)
Transfer 1──1 ProgressState (live display)
```
