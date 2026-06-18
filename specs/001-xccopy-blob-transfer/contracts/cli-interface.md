# Contract: `xccopy` CLI

The user-facing command contract. Maps to FR-001…FR-018 and User Stories 1–4.

## Synopsis

```text
xccopy SOURCE DESTINATION [--concurrency N] [--resume] [--block-size BYTES]
                          [--content-type TYPE] [--no-progress]
```

## Arguments

| Name | Required | Description |
|------|----------|-------------|
| `SOURCE` | yes | Source blob URI (`gs://bucket/key` or `az://account/container/key`). |
| `DESTINATION` | yes | Destination blob URI (same scheme set; may be a different cloud). |

## Options

| Option | Default | Description | Requirement |
|--------|---------|-------------|-------------|
| `--concurrency N` | `3` | Parallel block streams. Must be `1..32`. | FR-005, FR-006, FR-007 |
| `--resume` | off | Continue a prior interrupted transfer for this SOURCE→DESTINATION. | FR-009, FR-010 |
| `--block-size BYTES` | adaptive (≥8 MiB) | Override block size. Bounded by Azure limits. | research D6 |
| `--content-type TYPE` | inferred/source | Content-Type to set on the destination. | — |
| `--no-progress` | off | Suppress the live progress display (e.g. for non-TTY logs). | FR-014 |

## Behavior

- Without `--resume`: any existing checkpoint for this pair is cleared and the destination is
  overwritten by a fresh transfer (FR-008, FR-010).
- With `--resume`: re-stat the source; if the fingerprint differs from the checkpoint, **refuse**
  (FR-012). Otherwise transfer only blocks not already completed (FR-009).
- Progress is shown live by default (FR-014); reaches 100% only on verified completion (SC-008).
- On success, the destination object is finalized and integrity-verified (FR-013, FR-017).

## Exit codes (FR-018)

| Code | Meaning |
|------|---------|
| `0` | Success — destination written and integrity-verified. |
| `1` | Usage / input error (bad URI, invalid `--concurrency`, source missing, destination not writable). |
| `2` | Authentication error — required CLI session missing/expired (message names the exact command). |
| `3` | Resume refused — source changed since the interrupted run (FR-012). |
| `4` | Transfer/integrity failure after starting. |

## Output

- **Success** (stdout): `copied <source> -> <destination> (<size>, <duration>, verified)`.
- **Errors** (stderr): actionable message; auth errors name the exact `az login` /
  `gcloud auth application-default login` command (FR-015).
- No success output is produced on failure, and no partial destination object is left visible
  (FR-006 of US1 scenario 4, SC-006).
