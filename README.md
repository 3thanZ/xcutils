# xcutils

A toolbelt of **cross-cloud migration utilities**. Each tool helps move data and
resources between cloud providers — without ever handling long-lived service
account keys. xcutils authenticates by **reusing your existing cloud CLI sessions**.

| Utility  | Purpose                                                        |
| -------- | -------------------------------------------------------------- |
| `xccopy` | Stream an object from one cloud blob store to another.         |

## Why no service account keys?

xcutils never asks for, stores, or logs credentials. Instead it uses the sessions
the cloud CLIs already manage:

- **Azure** — `AzureCliCredential`, from your `az login` session.
- **Google Cloud** — Application Default Credentials, from
  `gcloud auth application-default login`.

If the required session is missing or expired, a utility fails immediately and tells
you exactly which command to run.

## Requirements

- Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/)
- Azure CLI (`az`) and/or Google Cloud SDK (`gcloud`) for the clouds you use

## Install

```bash
uv sync --extra dev
```

## Authenticate

Log in to the clouds you're moving data between:

```bash
az login
gcloud auth application-default login
```

### Required permissions

xccopy needs read access on the source and write access on the destination.
Assign these to the identity you authenticate with (not a service account key).

**Azure** — assign built-in roles on the relevant container or storage account:

| Role | When needed |
| ---- | ----------- |
| `Storage Blob Data Reader` | identity is reading from an Azure source |
| `Storage Blob Data Contributor` | identity is writing to an Azure destination |

> If both source and destination are in the same Azure account, assign
> `Storage Blob Data Contributor` (it includes read).

**GCP** — assign IAM roles on the relevant bucket:

| Role | When needed |
| ---- | ----------- |
| `roles/storage.objectViewer` | identity is reading from a GCS source |
| `roles/storage.objectAdmin` | identity is writing to a GCS destination |

> `roles/storage.objectCreator` is not sufficient for the destination because
> xccopy re-reads object metadata after the upload to verify integrity
> (`storage.objects.get`), which `objectCreator` does not grant.

#### Integration tests

Unit and contract tests (`uv run pytest`) are fully offline — no cloud credentials
required. Live integration tests (`XCCOPY_LIVE=1 uv run pytest tests/integration/`)
touch real cloud resources and need the same roles as production, scoped to the
test buckets/containers pointed to by `XCCOPY_TEST_SRC` and `XCCOPY_TEST_DST`.

## `xccopy` — streaming blob copy

Copy an object between clouds (or within one), streaming in bounded chunks so
arbitrarily large objects transfer with predictable memory use.

```bash
# Google Cloud Storage  ->  Azure Blob Storage
uv run xccopy gs://my-bucket/data/big.parquet az://myaccount/mycontainer/data/big.parquet

# Azure  ->  GCS
uv run xccopy az://myaccount/mycontainer/logs/app.log gs://my-bucket/logs/app.log
```

### Blob URI schemes

| Cloud                | URI form                                |
| -------------------- | --------------------------------------- |
| Google Cloud Storage | `gs://<bucket>/<object-path>`           |
| Azure Blob Storage   | `az://<account>/<container>/<blob-path>` |
| AWS S3               | `s3://<bucket>/<object-path>` *(reserved, not yet implemented)* |

Blocks stream from the source, through the host, straight to the destination — the whole
object is never assembled on the host, so a machine with little free space can move very
large objects. Reads run in parallel (default 3 streams), progress is shown live, and the
result is integrity-verified before success is reported.

### Options

- `--concurrency <n>` — parallel block streams, `1..32` (default 3).
- `--resume` — continue a prior interrupted transfer for this source→destination pair.
  Without it, a re-run starts fresh and overwrites. If the source changed since the
  interruption, `--resume` refuses (exit 3) rather than produce a corrupt object.
- `--block-size <bytes>` — override the (otherwise adaptive) block size.
- `--content-type <type>` — Content-Type to set on the destination object.
- `--no-progress` — suppress the live progress display (e.g. for non-TTY logs).

Resume state is kept locally under `${XDG_STATE_HOME:-~/.local/state}/xccopy/` and holds
only metadata — never object content or credentials. Azure destinations resume at block
granularity; for GCS destinations a resume currently restarts the upload (see the plan's
research notes for the planned multipart enhancement).

### Exit codes

`0` success · `1` usage/input error (bad URI, invalid option, source missing) ·
`2` authentication error (names the exact CLI login command) · `3` resume refused (source
changed) · `4` transfer/integrity failure.

## Development

This project uses **Spec-Driven Development** with the
[GitHub Spec Kit](https://github.com/github/spec-kit). Features are specified before
they're built:

```
/speckit-specify   → write the feature spec
/speckit-plan      → produce an implementation plan
/speckit-tasks     → break the plan into tasks
/speckit-implement → build it
```

Project principles live in [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

```bash
uv run pytest                        # tests (cloud-free unit tests by default)
uv run ruff check .                  # lint
uv run mypy                          # type-check
```

### Secret scanning (required — this is a public repo)

A [pre-commit](https://pre-commit.com) hook runs [gitleaks](https://github.com/gitleaks/gitleaks)
plus private-key/large-file checks on every commit, so secrets (and the service
account keys this project forbids) can't be committed accidentally. Enable it once
per clone:

```bash
uv tool install pre-commit     # or: pipx install pre-commit
pre-commit install             # installs the git pre-commit hook
```

Then it runs automatically on `git commit`. To scan the entire repo on demand:

```bash
pre-commit run --all-files
```

### Adding a new utility

1. Create `src/<utility>/` with its own `cli.py`.
2. Add an entry point under `[project.scripts]` in `pyproject.toml`.
3. Reuse `xcutils_common` for auth and URI parsing — don't duplicate them.

### Adding a new cloud

Implement a `BlobProvider` in `src/xccopy/providers/` and register it in
`providers/__init__.py`. Utilities pick it up automatically by URI scheme.

## License

MIT
