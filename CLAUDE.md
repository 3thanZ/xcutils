# xcutils — guidance for Claude Code

xcutils is a toolbelt of **cross-cloud migration utilities**. Each utility moves
data/resources between clouds (Azure, GCP, and others). The authoritative rules
live in `.specify/memory/constitution.md` — read it before making design changes.

## Non-negotiables (from the constitution)

1. **CLI-based auth only.** Never accept or store service account keys, connection
   strings, or credential files. Azure auth = `AzureCliCredential` (`az login`);
   GCP auth = Application Default Credentials (`gcloud auth application-default login`).
   All auth goes through `src/xcutils_common/auth.py`. Missing sessions must fail
   fast with the exact command the user should run.
2. **One utility per folder** under `src/`, each with its own `[project.scripts]`
   entry point in `pyproject.toml`. Shared code lives in `src/xcutils_common/` — do
   not duplicate it per utility.
3. **Stream, don't buffer.** Move data in bounded chunks; never load whole objects
   into memory or stage them fully on disk.
4. **Cross-cloud by abstraction.** Cloud specifics live behind the `BlobProvider`
   interface keyed by URI scheme (`gs://`, `az://`, `s3://`). Add a cloud by adding
   a provider in `src/xccopy/providers/` and registering it — don't touch utilities.

## Layout

```
src/
  xccopy/              # utility #1: streaming blob-to-blob copy
    cli.py             # typer CLI (entry point: `xccopy`)
    copier.py          # orchestration: stat -> plan -> engine -> verify -> checkpoint
    engine.py          # parallel block-transfer engine (thread pool + reorder buffer)
    blocks.py          # adaptive block planning (Azure 50k-block aware)
    checkpoint.py      # local, metadata-only resume state (no content/credentials)
    progress.py        # thread-safe progress + rich live display
    verify.py          # size/hash integrity check
    providers/         # BlobProvider + BlockSink impls + registry (azure, gcs)
  xcutils_common/      # shared: auth.py (CLI-session auth), uri.py (blob URIs)
tests/                 # pytest; unit/ + contract/ run offline, integration/ gated by XCCOPY_LIVE
  fakes.py             # in-memory provider/sink for offline contract tests
```

## Commands

```bash
uv sync --extra dev          # install deps + dev tools
uv run xccopy --help         # run the utility
uv run pytest                # tests
uv run ruff check . && uv run mypy   # lint + types

# Secret scanning (public repo). Enable once per clone:
uv tool install pre-commit && pre-commit install
pre-commit run --all-files   # scan everything on demand
```

Never commit secrets or service account keys. The `.pre-commit-config.yaml` hook
(gitleaks + detect-private-key) enforces this; `.gitignore` also blocks common
credential filenames.

## Workflow — Spec-Driven Development (GitHub Spec Kit)

Build features through Spec Kit skills, in order, before writing code:

`/speckit-constitution` → `/speckit-specify` → `/speckit-plan` → `/speckit-tasks`
→ `/speckit-implement`. Specs (`specs/`) and plans are the source of truth.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-xccopy-blob-transfer/plan.md` (with `research.md`, `data-model.md`,
`contracts/`, and `quickstart.md` alongside it).
<!-- SPECKIT END -->
