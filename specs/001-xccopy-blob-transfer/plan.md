# Implementation Plan: xccopy — cross-cloud blob copy

**Branch**: `001-xccopy-blob-transfer` | **Date**: 2026-06-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-xccopy-blob-transfer/spec.md`

## Summary

xccopy copies a single object between cloud blob stores by **streaming fixed-size blocks
through the host** — fetching byte ranges from the source in parallel (default 3 streams)
and forwarding them to the destination without ever assembling the whole object on the
host. Transfers are **resumable** via an explicit `--resume` flag backed by a local,
metadata-only checkpoint, **integrity-verified** on completion, and show **live progress**.

Technical approach: a cloud-agnostic block-transfer **engine** drives provider-specific
**ranged reads** (source) and **block sinks** (destination). Azure uses native parallel
block-blob staging (`stage_block` + `commit_block_list`); GCS uses an ordered resumable
upload fed by a bounded reorder buffer. Concurrency is a thread pool (the cloud SDKs are
blocking and the work is I/O-bound). Auth remains CLI-session only.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: typer (CLI), rich (progress; already present via typer),
azure-identity + azure-storage-blob (Azure), google-cloud-storage (GCP). No new top-level
dependency is required.

**Storage**: Local checkpoint files for resume state only (metadata: byte offsets, block
IDs / resumable-session URI, source fingerprint). Default location `~/.local/state/xccopy/`
(honors `$XDG_STATE_HOME`). **No object content is ever written to host storage.**

**Testing**: pytest. Unit + contract tests run offline with fakes; live cross-cloud copies
are integration tests gated behind an opt-in env var (e.g. `XCCOPY_LIVE=1`).

**Target Platform**: Linux/macOS host with network access to both clouds and the relevant
cloud CLI sessions established.

**Project Type**: Single-project Python CLI utility (one folder per utility under `src/`).

**Performance Goals**: For a large object (≥10 GB), default 3-way parallel reads complete
≥40% faster than a single stream (SC-002); throughput should approach the narrower of the
two clouds' bandwidth.

**Constraints**: Host memory + local storage footprint bounded by roughly
`(concurrency + reorder_window) × block_size`, **independent of object size** (FR-021,
SC-004/SC-007). No whole-object staging on host. CLI-auth only; no key material. Exit
non-zero on any failure (FR-018).

**Scale/Scope**: One object per invocation (0 bytes → multi-TB). Concurrency default 3,
bounded to a safe maximum (32). Adaptive block size so Azure's 50,000-block limit is never
exceeded.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. CLI-Based Authentication Only | ✅ PASS | Reuses `AzureCliCredential` + GCP ADC via `xcutils_common.auth`. No keys read/stored/logged. Checkpoints hold metadata only (FR-022), never tokens. |
| II. One Utility Per Folder | ✅ PASS | All new code under `src/xccopy/`; shared concerns stay in `src/xcutils_common/`. No duplication. |
| III. Streaming Over Buffering | ✅ PASS | Core design: bounded per-block streaming through the host; footprint independent of object size. |
| IV. Cross-Cloud By Abstraction | ✅ PASS | New `stat`/`read_block`/`open_sink` capabilities live behind `BlobProvider`; the engine is cloud-neutral and resolves providers by URI scheme. |
| V. Spec-Driven Development | ✅ PASS | Plan derived from spec FR-001…FR-022 and SC-001…SC-008. |
| Tech constraints (Py3.12/uv/typer/ruff/mypy/pytest) | ✅ PASS | Unchanged; `rich` already present transitively. |

**Result**: PASS — no violations. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/001-xccopy-blob-transfer/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI, provider interface, checkpoint schema)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/xccopy/
├── __init__.py
├── cli.py                 # add --concurrency, --resume, --block-size, --content-type; wire progress
├── copier.py              # orchestration: stat source → plan blocks → run engine → verify → checkpoint lifecycle
├── engine.py              # NEW: parallel block-transfer engine (thread pool + bounded reorder buffer)
├── checkpoint.py          # NEW: local, metadata-only resume state keyed by (source, destination)
├── progress.py            # NEW: thread-safe progress aggregation + rich rendering
└── providers/
    ├── __init__.py        # registry (unchanged)
    ├── base.py            # extend: ObjectStat, stat(), read_block(); BlockSink ABC + open_sink()
    ├── azure.py           # ranged read; block-blob sink (stage_block / commit_block_list)
    └── gcs.py             # ranged read; ordered resumable-upload sink

src/xcutils_common/        # unchanged (auth.py, uri.py)

tests/
├── unit/                  # uri, block planning, checkpoint, progress math, reorder-buffer ordering
├── contract/              # BlobProvider/BlockSink conformance via in-memory fakes
└── integration/           # live cross-cloud copy + resume (opt-in: XCCOPY_LIVE=1)
```

**Structure Decision**: Single-project CLI layout, extending the existing `src/xccopy/`
package. New modules (`engine.py`, `checkpoint.py`, `progress.py`) isolate the parallel
transfer, resume, and progress concerns; the provider interface in `providers/base.py` gains
ranged-read and block-sink capabilities so the engine stays cloud-agnostic. The existing
`tests/test_uri.py` moves under `tests/unit/`.

## Complexity Tracking

> No constitution violations — section intentionally empty.
