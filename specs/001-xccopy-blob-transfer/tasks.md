---
description: "Task list for xccopy — cross-cloud blob copy"
---

# Tasks: xccopy — cross-cloud blob copy

**Input**: Design documents from `/specs/001-xccopy-blob-transfer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — the constitution requires tests for provider interfaces, URI parsing,
and auth preflight, with live cloud calls as opt-in integration tests (`XCCOPY_LIVE=1`).

**Organization**: Grouped by user story. Priority order: US1 (P1) → US2 (P2) → US4 (P2) →
US3 (P3). Each story is an independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4 (matches spec.md user stories)

## Path Conventions

Single-project Python CLI: code under `src/`, tests under `tests/` (see plan.md structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test layout and dependency declarations.

- [X] T001 Reorganize tests into `tests/unit/`, `tests/contract/`, `tests/integration/`; move existing `tests/test_uri.py` → `tests/unit/test_uri.py`; update `testpaths`/`pythonpath` in `pyproject.toml`
- [X] T002 Add `rich>=13` to `[project.dependencies]` in `pyproject.toml` (used directly for progress; currently only transitive via typer)
- [X] T003 [P] Add opt-in live-integration config: a `live` pytest marker plus an autouse skip keyed on `XCCOPY_LIVE` in `tests/integration/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cloud-agnostic types and the extended provider/sink contract that every story builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Implement `Block`, `BlockPlan`, and adaptive `plan_blocks(size, block_size)` (default 8 MiB, grow to keep block count ≤ 50000, cap 4000 MiB) in `src/xccopy/blocks.py`
- [X] T005 Extend the provider contract in `src/xccopy/providers/base.py`: add `ObjectStat` dataclass, abstract `stat()`, `read_block()`, `open_sink()` on `BlobProvider`, and the `BlockSink` ABC + `CommitResult` (per contracts/provider-interface.md) — depends on T004
- [X] T006 [P] Implement in-memory fake `BlobProvider` + fake `BlockSink` (both ordered and unordered modes) for tests in `tests/contract/fakes.py` — depends on T005
- [X] T007 [P] Generic provider/sink conformance contract tests (round-trip equals source, ordered vs unordered staging, `already_done()` resume, content-free `resume_state()`, zero-byte) parametrized over fakes in `tests/contract/test_provider_contract.py` — depends on T005, T006
- [X] T008 [P] Unit tests for block planning (adaptive size, 50k cap, last-block length, zero-byte) in `tests/unit/test_blocks.py` — depends on T004

**Checkpoint**: Contract + types ready — user stories can begin.

---

## Phase 3: User Story 1 - Copy an object between clouds (Priority: P1) 🎯 MVP

**Goal**: Correctly copy one object source→destination (cross-cloud or same-cloud), streaming
blocks through the host, and integrity-verify the result.

**Independent Test**: With both CLIs authenticated, copy an object `gs://…` → `az://…`; the
destination exists and matches the source byte-for-byte (quickstart Scenario 1).

### Tests for User Story 1

- [X] T009 [P] [US1] Unit test for Azure block-id encoding/decoding and ordered commit-list construction in `tests/unit/test_azure_sink.py`
- [X] T010 [P] [US1] Integration test: `gs://→az://` and `az://→gs://` copy with size + hash verification, gated by `XCCOPY_LIVE`, in `tests/integration/test_copy_cross_cloud.py`

### Implementation for User Story 1

- [X] T011 [P] [US1] Implement `stat()` and ranged `read_block()` for Azure in `src/xccopy/providers/azure.py`
- [X] T012 [US1] Implement `AzureBlockBlobSink` (`stage_block` + `commit_block_list`, per-block Content-MD5, `requires_ordered=False`, `already_done()`/`resume_state()`) and `open_sink()` in `src/xccopy/providers/azure.py` — depends on T011
- [X] T013 [P] [US1] Implement `stat()` and ranged `read_block()` for GCS in `src/xccopy/providers/gcs.py`
- [X] T014 [US1] Implement `GcsResumableSink` (ordered resumable upload, crc32c/md5, `requires_ordered=True`, `already_done()`/`resume_state()`) and `open_sink()` in `src/xccopy/providers/gcs.py` — depends on T013
- [X] T015 [P] [US1] Implement on-the-fly integrity verification (streaming hash, size + hash compare against source/destination) in `src/xccopy/verify.py`
- [X] T016 [US1] Implement the block-transfer engine baseline (single in-flight stream: fetch block → stage respecting `requires_ordered` → commit; on-the-fly hashing; zero-byte handling) in `src/xccopy/engine.py` — depends on T005, T012, T014, T015
- [X] T017 [US1] Rewrite `copier.copy()`: `stat` source → `plan_blocks` → `open_sink` → run engine → verify → return `CopyResult` in `src/xccopy/copier.py` — depends on T016
- [X] T018 [US1] Update CLI (`SOURCE`, `DESTINATION`, `--content-type`); map outcomes to exit codes 0/1/2/4; actionable auth-error message naming `az login` / `gcloud auth application-default login` in `src/xccopy/cli.py` — depends on T017
- [X] T019 [US1] Handle error edges (missing source → exit 1, destination not writable → exit 1, no partial destination on failure) in `src/xccopy/copier.py` / `engine.py` — depends on T017

**Checkpoint**: A correct single-object cross-cloud copy works end-to-end (MVP).

---

## Phase 4: User Story 2 - Speed up large transfers with parallel streaming (Priority: P2)

**Goal**: Transfer blocks concurrently (default 3, overridable), with a bounded reorder buffer.

**Independent Test**: Copy a ≥10 GB object with `--concurrency 1` vs `3`; the 3-stream run is
≥40% faster for an Azure destination (quickstart Scenario 2).

### Tests for User Story 2

- [X] T020 [P] [US2] Unit test: invalid `--concurrency` (0, negative, >32) rejected before any I/O in `tests/unit/test_concurrency_validation.py`
- [X] T021 [P] [US2] Unit test: bounded reorder buffer preserves index order for ordered sinks and caps in-flight blocks in `tests/unit/test_reorder_buffer.py`
- [X] T025 [P] [US2] Integration test: 3-stream vs 1-stream timing on a large object, gated by `XCCOPY_LIVE`, in `tests/integration/test_parallel.py`

### Implementation for User Story 2

- [X] T022 [US2] Add `ThreadPoolExecutor`-based parallel block fetch with a bounded reorder buffer (`max_workers=concurrency`) to `src/xccopy/engine.py` — depends on T016
- [X] T023 [US2] Add `--concurrency` option (default 3) with `1..32` validation in `src/xccopy/cli.py` — depends on T018
- [X] T024 [US2] Add `--block-size` override validated against adaptive bounds in `src/xccopy/cli.py` — depends on T018

**Checkpoint**: Copies run in parallel with bounded host memory; US1 still passes.

---

## Phase 5: User Story 4 - See copy progress (Priority: P2)

**Goal**: Live, continuously-updating progress (bytes, %, throughput, ETA) reaching 100% only on
verified completion.

**Independent Test**: Copy a large object and observe progress updating ≥ every few seconds and
finishing at 100% (quickstart; SC-008).

### Tests for User Story 4

- [X] T026 [P] [US4] Unit test: thread-safe `ProgressState` aggregation and resumed-bytes initialization in `tests/unit/test_progress.py`

### Implementation for User Story 4

- [X] T027 [P] [US4] Implement `ProgressState` + `rich`-based renderer (bytes, percentage, throughput, ETA) in `src/xccopy/progress.py`
- [X] T028 [US4] Wire the engine to report completed-byte deltas via a thread-safe callback in `src/xccopy/engine.py` — depends on T022, T027
- [X] T029 [US4] Add live progress to the CLI plus a `--no-progress` flag for non-TTY use in `src/xccopy/cli.py` — depends on T023

**Checkpoint**: Progress is visible; US1/US2 still pass.

---

## Phase 6: User Story 3 - Resume an interrupted transfer (Priority: P3)

**Goal**: With `--resume`, continue an interrupted transfer (skip completed blocks); without it,
start fresh and overwrite; refuse resume when the source changed.

**Independent Test**: Interrupt a large copy, re-run with `--resume`; completed blocks are not
re-sent and the result verifies. Changed source → refuse with exit 3 (quickstart Scenario 3).

### Tests for User Story 3

- [X] T030 [P] [US3] Unit test: checkpoint atomic write, `0600` perms, content-free, forward-compatible `version` handling in `tests/unit/test_checkpoint.py`
- [X] T031 [P] [US3] Unit test: resume refused (exit 3) on source-fingerprint mismatch in `tests/unit/test_resume_guard.py`
- [X] T036 [P] [US3] Integration test: interrupt + `--resume` continues and skips completed blocks; changed-source refusal, gated by `XCCOPY_LIVE`, in `tests/integration/test_resume.py`

### Implementation for User Story 3

- [X] T032 [P] [US3] Implement the checkpoint module (XDG state path, atomic temp+rename write, load/save/delete, schema v1 per contracts/checkpoint-schema.md) in `src/xccopy/checkpoint.py`
- [X] T033 [US3] Engine: on resume, seed from `sink.already_done()` and skip completed blocks; persist checkpoint as blocks complete; delete on successful commit in `src/xccopy/engine.py` — depends on T028, T032
- [X] T034 [US3] `copier`: load/clear checkpoint, compare source fingerprint (refuse on mismatch), and on a fresh (non-resume) run clear the checkpoint and overwrite in `src/xccopy/copier.py` — depends on T033
- [X] T035 [US3] CLI: add `--resume` flag and exit code 3 on refusal in `src/xccopy/cli.py` — depends on T029

**Checkpoint**: All four user stories work independently.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T037 [P] Update the `xccopy` section of `README.md` (document `--concurrency`, `--resume`, `--block-size`, `--no-progress`, and how progress/resume behave)
- [X] T038 [P] Update `CLAUDE.md` layout notes for the new modules (`engine.py`, `blocks.py`, `checkpoint.py`, `progress.py`, `verify.py`)
- [X] T039 Run all `quickstart.md` scenarios (1–5) and record results
- [X] T040 [P] Make `ruff check` and `mypy --strict` clean across all new modules
- [X] T041 Security check: confirm no object content or credentials appear in checkpoints or logs (FR-022, Constitution Principle I)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: after Setup — BLOCKS all user stories.
- **User Stories (Phases 3–6)**: all require Foundational. US1 is the MVP; US2/US4/US3 build on
  the US1 engine/CLI and are layered in priority order.
- **Polish (Phase 7)**: after the desired stories are complete.

### User Story Dependencies

- **US1 (P1)**: only Foundational. Delivers a usable product alone.
- **US2 (P2)**: extends the US1 engine (T022 ← T016) and CLI (T023/T024 ← T018).
- **US4 (P2)**: extends the engine with progress callbacks (T028 ← T022) and CLI (T029 ← T023).
- **US3 (P3)**: adds checkpointing on top of the engine (T033 ← T028) and CLI (T035 ← T029).
  Note: the sinks already expose `already_done()`/`resume_state()` from US1, so US3 adds only
  persistence, the fingerprint guard, and the flag.

### Within Each User Story

Tests written first and expected to fail → providers/types → engine → copier → CLI.

### Parallel Opportunities

- Setup: T003 ∥ (T001→T002 share `pyproject.toml`).
- Foundational: after T004→T005, then T006 ∥ T007 ∥ T008.
- US1: T009 ∥ T010 (tests); T011 ∥ T013 ∥ T015 (different files); sinks T012/T014 follow their reads.
- US2: T020 ∥ T021 ∥ T025.
- US3: T030 ∥ T031 ∥ T032 ∥ T036.

---

## Parallel Example: User Story 1

```bash
# Tests first (different files):
Task: "Unit test Azure block-id encoding in tests/unit/test_azure_sink.py"   # T009
Task: "Integration cross-cloud copy test in tests/integration/test_copy_cross_cloud.py"  # T010

# Then independent reads + verify (different files):
Task: "Azure stat()/read_block() in src/xccopy/providers/azure.py"   # T011
Task: "GCS stat()/read_block() in src/xccopy/providers/gcs.py"       # T013
Task: "Integrity verification in src/xccopy/verify.py"               # T015
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & validate** (quickstart
   Scenario 1) → demo a working cross-cloud copy.

### Incremental Delivery

US1 (correct copy) → US2 (faster) → US4 (visible) → US3 (resumable). Each ships independently and
is validated against its quickstart scenario without breaking prior stories.

---

## Notes

- `[P]` = different files, no incomplete dependency.
- Live cloud tests are skipped unless `XCCOPY_LIVE=1`; unit/contract suites run offline via fakes.
- The host never stores the whole object and checkpoints hold metadata only — verify in T041.
- Task IDs are globally sequential; within US2/US3 the integration test ID (T025/T036) sorts after
  its sibling implementation tasks but can be written first.
- Commit after each task or logical group.
