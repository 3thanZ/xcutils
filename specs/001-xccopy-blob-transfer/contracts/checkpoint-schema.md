# Contract: Checkpoint file schema

Durable, machine-local resume state (FR-011). **Metadata only — no object bytes, no
credentials** (FR-022).

- **Location**: `${XDG_STATE_HOME:-$HOME/.local/state}/xccopy/`
- **Filename**: `<sha256(source_uri + "\0" + destination_uri)>.json`
- **Permissions**: file mode `0600`, directory `0700`.

## Schema (v1)

```json
{
  "version": 1,
  "source_uri": "gs://my-bucket/data/big.parquet",
  "destination_uri": "az://myacct/mycontainer/data/big.parquet",
  "source_fingerprint": "generation:1712345678901234",
  "block_size": 8388608,
  "total_size": 53687091200,
  "completed_blocks": [0, 1, 2, 5],
  "sink_state": {
    "kind": "azure-block-blob",
    "block_ids": { "0": "MDAwMDA=", "1": "MDAwMDE=" }
  },
  "created_at": "2026-06-18T20:00:00Z",
  "updated_at": "2026-06-18T20:03:11Z"
}
```

`sink_state` is sink-specific:

- **Azure** (`kind: "azure-block-blob"`): map of block index → base64 block id for staged blocks.
- **GCS** (`kind: "gcs-resumable"`): `{ "session_uri": "...", "committed_offset": 41943040 }`.

## Rules

- On `--resume`: load by filename; require `source_uri` + `destination_uri` to match the request
  and `source_fingerprint` to equal the current `stat()` — otherwise **refuse** (exit 3, FR-012).
- `completed_blocks` and `sink_state` MUST stay consistent; a block is "done" only once
  server-side staging succeeded.
- Write atomically (temp file + rename) so an interrupted update never corrupts the checkpoint.
- **Delete** the file on successful `commit` (FR-017); **clear** it at the start of a fresh
  (non-`--resume`) run for the same pair (FR-008/FR-010).
- A reader MUST tolerate unknown future fields (forward-compatible); a `version` it does not
  understand is treated as "no usable checkpoint" (fall back to fresh transfer).
