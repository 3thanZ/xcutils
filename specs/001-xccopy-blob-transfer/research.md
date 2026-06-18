# Phase 0 Research: xccopy

All decisions below resolve design unknowns implied by the spec (FR-004…FR-022,
SC-002…SC-008). The technology stack itself was fixed by the project constitution, so it is
not re-litigated here.

## D1. Concurrency model — threads, not async

- **Decision**: Use a `concurrent.futures.ThreadPoolExecutor` with `max_workers = concurrency`
  (default 3) for parallel block transfers.
- **Rationale**: The work is network-I/O-bound, and the chosen SDKs (`azure-storage-blob`,
  `google-cloud-storage`) are synchronous/blocking. Threads release the GIL during I/O, so
  N blocking calls run concurrently. This avoids dragging in async SDK variants and keeps the
  code shape close to the existing scaffold.
- **Alternatives considered**: `asyncio` + `aio` SDKs (more invasive, two code paths, GCS
  async support is weaker); multiprocessing (needless overhead, IPC of byte blocks).

## D2. Engine architecture — ranged reads + block sink + bounded reorder buffer

- **Decision**: A cloud-agnostic engine: (1) `stat` the source for size + fingerprint;
  (2) split into fixed-size blocks (byte ranges); (3) worker threads issue **ranged reads**
  against the source provider; (4) blocks are handed to a destination **`BlockSink`**.
  A `BlockSink` declares `requires_ordered`. If ordered, the engine delivers blocks in index
  order from a **bounded reorder buffer**; if not, it stages blocks as soon as they arrive.
- **Rationale**: Cleanly absorbs the asymmetry between the two clouds (D3/D4) behind one
  interface. The bounded reorder buffer caps host memory at roughly
  `(concurrency + reorder_window) × block_size`, satisfying FR-021 / SC-004 / SC-007.
- **Alternatives considered**: Per-cloud bespoke pipelines (violates Principle IV, duplicates
  progress/resume logic); unbounded queue (breaks the memory bound).

## D3. Azure destination — native block-blob staging (parallel, unordered)

- **Decision**: Implement the Azure sink with **Block Blobs**: `stage_block(block_id, data)`
  per block (parallel, any order), then `commit_block_list([...])` in index order to assemble.
- **Rationale**: This is Azure's first-class parallel-upload + resumable primitive. Staged but
  uncommitted blocks persist service-side (~7 days), so resume = re-stat, re-stage only missing
  block IDs, then commit. `requires_ordered = False`.
- **Constraints**: Max 50,000 blocks per blob and max block 4000 MiB → drives adaptive block
  size (D6). Per-block `Content-MD5` can be supplied for integrity (D7).
- **Alternatives considered**: `upload_blob(stream)` (current scaffold) — single-stream, not
  parallel, not block-resumable.

## D4. GCS destination — ordered resumable upload (read-side parallelism)

- **Decision**: Implement the GCS sink with a **resumable upload session** that consumes blocks
  **in order** (`requires_ordered = True`). The engine still fetches source ranges in parallel
  and reorders before handing them to the sink. Resume = persist the session URI + last
  committed offset; on `--resume`, query the session and continue from that offset.
- **Rationale**: GCS resumable upload is the well-supported, natively resumable upload path and
  needs no destination-side temp objects. Read-side parallelism still helps when the source read
  is the bottleneck (common cross-cloud), and the host footprint stays bounded.
- **Known limitation**: the **write** leg to GCS is serial. For GCS-destination transfers, the
  ≥40% speedup (SC-002) is realized when the source-read leg dominates; it is most clearly met
  for Azure destinations. Documented as accepted for v1.
- **Future enhancement**: GCS XML multipart upload (S3-compatible MPU) would allow parallel part
  uploads mirroring Azure's model — revisit if write-side parallelism for GCS becomes a goal.
- **Alternatives considered**: upload N temp objects + `compose` (≤32 components, chaining
  complexity, destination-side artifacts to clean up); `transfer_manager.upload_chunks_concurrently`
  (operates on local files, contradicts the no-host-storage requirement).

## D5. Ranged reads (source)

- **Decision**: Azure — `download_blob(offset=…, length=…)`; GCS —
  `blob.download_as_bytes(start=…, end=…)`. Both stream a single block's bytes.
- **Rationale**: Range requests are the basis of parallel reads and of re-reading only missing
  blocks on resume. Add `read_block(location, offset, length)` to the provider interface.

## D6. Adaptive block size

- **Decision**: Default block size 8 MiB. Before transfer, compute
  `block_size = max(8 MiB, round_up_pow2(ceil(source_size / 50000)))` so Azure's 50,000-block
  cap is never exceeded; `--block-size` overrides. Bounded to Azure's 4000 MiB max.
- **Rationale**: Keeps small/medium objects efficient while supporting multi-TB objects.
- **Alternatives considered**: Fixed 8 MiB (fails above ~390 GB on Azure); per-cloud sizes
  (needless divergence).

## D7. Integrity verification (FR-013, SC-005)

- **Decision**: Compute a content hash **on the fly** while streaming (never from a staged
  file). Always verify **byte size** end-to-end. Supply per-block `Content-MD5` to Azure
  `stage_block` and the full checksum (crc32c/md5) to the GCS session so each service validates
  server-side; after finalize, compare the destination's reported hash to the locally computed
  one, and to the source's reported hash when the source exposes one.
- **Rationale**: Pass-through compatible (no staged file), catches corruption at block and object
  level. Cross-cloud stored-hash availability is inconsistent, so the host-computed hash is the
  source of truth.
- **Alternatives considered**: Trust stored hashes only (Azure `Content-MD5` is often absent);
  re-download to compare (doubles transfer, violates bounded footprint).

## D8. Source fingerprint for safe resume (FR-012)

- **Decision**: Capture a source fingerprint at first run — Azure **ETag**, GCS **generation**
  (plus size) — and store it in the checkpoint. On `--resume`, re-`stat` and compare; on
  mismatch, **refuse** and tell the user to restart (no `--resume`).
- **Rationale**: Prevents stitching old + new source data into a corrupt object.

## D9. Checkpoint storage (FR-011, FR-022)

- **Decision**: One JSON file per transfer under `${XDG_STATE_HOME:-~/.local/state}/xccopy/`,
  filename = hex SHA-256 of `f"{source_uri}\0{destination_uri}"`. Contents = **metadata only**:
  source/dest URIs, source fingerprint, block size, total size, per-block status, Azure block-ID
  list or GCS session URI + offset, timestamps. **No object bytes.**
- **Lifecycle**: created when the first block is staged; updated as blocks complete; **deleted on
  successful commit**; on a fresh (non-`--resume`) run, any existing checkpoint is cleared and the
  destination overwritten (FR-008/FR-010).
- **Rationale**: Durable, machine-local, inspectable, and never holds content or credentials.
- **Alternatives considered**: Destination object metadata (cross-cloud inconsistency);
  remembering nothing (no resume).

## D10. Live progress (FR-014, US4, SC-008)

- **Decision**: Use `rich.progress` (already available via typer) with a single task showing
  bytes transferred, percentage, throughput, and ETA. The engine reports completed-byte deltas
  through a thread-safe callback; on `--resume`, initialize completed bytes to the already-staged
  amount so the bar does not restart at zero.
- **Rationale**: No new dependency; thread-safe aggregation fits the thread-pool model; satisfies
  "updates at least every few seconds."
- **Alternatives considered**: `tqdm` (extra dependency); print statements (no live redraw).

## D11. Edge cases

- **Zero-byte object**: skip block transfer; Azure commits an empty block list, GCS finalizes an
  empty upload. Integrity check = size 0.
- **Abort/failure (FR-020)**: release in-memory buffers immediately; leave service-side staged
  blocks / resumable session for a future `--resume`; the host retains nothing. A fresh run with
  no `--resume` discards prior server-side state where cheaply possible and overwrites.
- **Invalid concurrency (FR-007)**: reject `< 1` or `> 32` before any I/O.
