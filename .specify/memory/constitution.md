# xcutils Constitution

xcutils is a toolbelt of cross-cloud migration utilities. Each utility helps move
data and resources between cloud providers (Azure, Google Cloud, and others) without
ever handling long-lived service account keys.

## Core Principles

### I. CLI-Based Authentication Only (NON-NEGOTIABLE)
Utilities MUST authenticate by reusing the user's existing cloud CLI session, never
by accepting service account keys, connection strings, or downloaded credential files.
- Azure access uses `AzureCliCredential` (the session established by `az login`).
- Google Cloud access uses Application Default Credentials established by
  `gcloud auth application-default login`.
- xcutils MUST NOT read, write, persist, or log raw credentials. If a required CLI
  session is missing or expired, the utility MUST fail fast with a clear message
  telling the user exactly which command to run.

### II. One Utility Per Folder
Every utility is a self-contained package in its own folder under `src/` with its own
CLI entry point declared in `pyproject.toml` `[project.scripts]`.
- A utility owns its CLI, orchestration, and tool-specific logic.
- Cross-cutting concerns (authentication, URI parsing, provider interfaces) live in
  the shared `src/xcutils_common/` package — never duplicated per utility.
- A utility must be usable and testable in isolation.

### III. Streaming Over Buffering
Data MUST move in bounded chunks. Utilities MUST NOT load whole objects into memory
or stage them fully on local disk.
- Transfers stream source -> destination so arbitrarily large objects are supported
  with bounded, predictable memory use.
- Chunk size is configurable; defaults favor correctness and modest memory.

### IV. Cross-Cloud By Abstraction
Cloud-specific behavior lives behind a common provider interface keyed by URI scheme
(`gs://`, `az://`, `s3://`, ...).
- Utilities operate against the abstraction, never a specific cloud SDK directly.
- Adding support for a new cloud means adding a provider, not editing every utility.

### V. Spec-Driven Development
Features flow through the GitHub Spec Kit workflow before implementation:
`/speckit-constitution` -> `/speckit-specify` -> `/speckit-plan` -> `/speckit-tasks`
-> `/speckit-implement`. Specs and plans are the source of truth; code follows them.
This constitution governs every spec and plan.

## Technology Constraints

- Language: Python >= 3.12.
- Environment & packaging: `uv` for dependency management and execution.
- CLI framework: `typer`.
- Cloud SDKs: `azure-identity` + `azure-storage-blob` (Azure), `google-cloud-storage`
  (GCP). New clouds add their own SDK plus a provider implementation.
- Quality gates: `ruff` (lint/format), `mypy --strict` (typing), `pytest` (tests).

## Development Workflow

- Each feature begins with a spec under `specs/` created via `/speckit-specify`.
- Plans and tasks are generated with `/speckit-plan` and `/speckit-tasks`.
- Implementation MUST satisfy the spec and obey this constitution.
- Tests cover provider interfaces, URI parsing, and auth-preflight behavior. Live
  cloud calls are integration tests, gated behind an explicit opt-in.

## Governance

This constitution supersedes other practices. Any change that conflicts with a
principle must either be revised or the constitution amended first. Amendments are
documented here with an updated version and date. Complexity must be justified
against the principles above; prefer the simplest design that satisfies the spec.

**Version**: 1.0.0 | **Ratified**: 2026-06-18 | **Last Amended**: 2026-06-18
