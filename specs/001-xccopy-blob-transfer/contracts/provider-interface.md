# Contract: `BlobProvider` + `BlockSink`

Extends the existing `BlobProvider` (in `src/xccopy/providers/base.py`) so the engine stays
cloud-agnostic (Constitution Principle IV). New providers implement these; the engine depends
only on this contract.

## `BlobProvider` (additions)

```python
class BlobProvider(abc.ABC):
    scheme: str  # existing

    def stat(self, location: BlobLocation) -> ObjectStat: ...
    #   Return size, fingerprint (ETag/generation), content_type, optional source_hash.
    #   Raise FileNotFoundError-equivalent if the source object does not exist (-> exit 1).

    def read_block(self, location: BlobLocation, offset: int, length: int) -> bytes: ...
    #   Ranged read of exactly [offset, offset+length) (last block may be shorter).
    #   Must be safe to call concurrently from multiple threads.

    def open_sink(
        self,
        location: BlobLocation,
        *,
        total_size: int,
        block_size: int,
        content_type: str | None,
        resume_state: dict | None,   # None => fresh transfer
    ) -> "BlockSink": ...
    #   Create/resume a destination sink. resume_state is the checkpoint's sink_state.
```

*(The existing `open_read` / `write` whole-object methods remain for simple cases and backward
compatibility; the engine uses the block-oriented methods above.)*

## `BlockSink`

```python
class BlockSink(abc.ABC):
    requires_ordered: bool
    #   True  -> engine must call stage() in ascending block index order (GCS resumable upload).
    #   False -> stage() may be called in any order / concurrently (Azure block staging).

    def already_done(self) -> set[int]: ...
    #   Block indices already persisted server-side (from resume_state). Empty for fresh.

    def stage(self, block: Block, data: bytes) -> None: ...
    #   Persist one block server-side with a per-block integrity check where supported.
    #   For ordered sinks, called sequentially; for unordered, may run on worker threads.

    def commit(self, ordered_indices: list[int]) -> CommitResult: ...
    #   Finalize/assemble the object in index order. Returns CommitResult(size, dest_hash).

    def abort(self) -> None: ...
    #   Release engine-side resources. Server-side staged state MAY persist to allow --resume.

    def resume_state(self) -> dict: ...
    #   JSON-serializable metadata for the checkpoint (Azure: block-id list; GCS: session URI +
    #   committed offset). MUST NOT contain object bytes or credentials (FR-022).
```

## Concurrency & integrity obligations

- `read_block` and (for unordered sinks) `stage` MUST be thread-safe.
- Sinks SHOULD pass a per-block checksum to the service; `commit` MUST surface the destination's
  size/hash so the engine can verify against the host-computed hash (FR-013, SC-005).
- No method may write object content to host storage (FR-019, FR-020).

## Conformance tests (contract suite)

`tests/contract/` exercises any `BlobProvider`/`BlockSink` pair (including in-memory fakes) for:
round-trip block transfer == source bytes; ordered vs unordered staging honored;
`already_done()` drives correct resume; `resume_state()` is JSON-serializable and content-free;
zero-byte object; size/hash verification on `commit`.
