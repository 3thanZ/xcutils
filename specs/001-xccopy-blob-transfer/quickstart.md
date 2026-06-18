# Quickstart & Validation: xccopy

End-to-end scenarios that prove the feature meets the spec. Contracts and entities are not
duplicated here — see [contracts/](./contracts/) and [data-model.md](./data-model.md).

## Prerequisites

```bash
uv sync --extra dev
az login                                      # Azure CLI session (FR-003)
gcloud auth application-default login         # GCP Application Default Credentials (FR-003)
```

You need read access to a source object and write access to a destination bucket/container in
the relevant clouds. Live scenarios are opt-in:

```bash
export XCCOPY_LIVE=1
export XCCOPY_TEST_SRC="gs://my-bucket/fixtures/medium.bin"     # ~1–10 GB recommended
export XCCOPY_TEST_DST="az://myacct/mycontainer/fixtures/medium.bin"
```

## Scenario 1 — Cross-cloud copy (US1, FR-001/002/013)

```bash
uv run xccopy "$XCCOPY_TEST_SRC" "$XCCOPY_TEST_DST"
```

**Expect**: live progress to 100%; final line `copied … -> … (<size>, <duration>, verified)`;
exit 0. Destination object exists and its size/hash match the source.

## Scenario 2 — Parallel streaming speedup (US2, SC-002)

```bash
time uv run xccopy "$XCCOPY_TEST_SRC" "$XCCOPY_TEST_DST" --concurrency 1
time uv run xccopy "$XCCOPY_TEST_SRC" "$XCCOPY_TEST_DST" --concurrency 3   # default
```

**Expect**: for a ≥10 GB object with an Azure destination, the 3-stream run is ≥40% faster.
Invalid values fail fast before any I/O:

```bash
uv run xccopy "$XCCOPY_TEST_SRC" "$XCCOPY_TEST_DST" --concurrency 0   # exit 1, clear error
```

## Scenario 3 — Resume an interrupted transfer (US3, FR-009/010/012)

```bash
uv run xccopy "$XCCOPY_TEST_SRC" "$XCCOPY_TEST_DST"      # Ctrl-C partway through
uv run xccopy "$XCCOPY_TEST_SRC" "$XCCOPY_TEST_DST" --resume
```

**Expect**: the resumed run skips completed blocks (progress does not restart at 0) and finishes
with a verified, correct object. A re-run **without** `--resume` starts fresh and overwrites.
If the source changed since interruption, `--resume` refuses with exit 3.

## Scenario 4 — Bounded host footprint (FR-019/020/021, SC-004/007)

On a host with far less free disk/RAM than the object (or while watching RSS):

```bash
/usr/bin/time -v uv run xccopy "$XCCOPY_TEST_SRC" "$XCCOPY_TEST_DST" --concurrency 3
```

**Expect**: peak memory stays near `(concurrency + reorder_window) × block_size` regardless of
object size; no temporary file containing object data appears on the host during or after the
run.

## Scenario 5 — Missing auth (FR-015, SC-006)

```bash
az logout
uv run xccopy "az://myacct/myc/obj" "gs://my-bucket/obj"
```

**Expect**: immediate exit 2, message naming `az login`, no progress, no partial destination.

## Offline checks (no cloud needed)

```bash
uv run pytest          # unit + contract suites (fakes); live tests skipped unless XCCOPY_LIVE=1
uv run ruff check . && uv run mypy
```
