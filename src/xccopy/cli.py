"""Command-line interface for xccopy."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Annotated

import typer

from xccopy.copier import SourceChangedError, copy
from xccopy.progress import live_progress
from xccopy.verify import IntegrityError
from xcutils_common.auth import AuthError

app = typer.Typer(
    add_completion=False,
    help=(
        "Stream a blob from one cloud to another, in parallel, with resume and integrity "
        "checks. Authentication uses your cloud CLI sessions only (az login / "
        "gcloud auth application-default login) — never service account keys."
    ),
)


def _progress_factory(
    enabled: bool,
) -> Callable[[int, str], AbstractContextManager[Callable[[int], None] | None]]:
    def factory(total: int, label: str) -> AbstractContextManager[Callable[[int], None] | None]:
        return live_progress(total, label, enabled=enabled)

    return factory


def _fail(message: str, code: int) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(code=code)


@app.command()
def main(
    source: Annotated[
        str,
        typer.Argument(help="Source blob URI, e.g. gs://bucket/path or az://acct/container/path"),
    ],
    destination: Annotated[str, typer.Argument(help="Destination blob URI.")],
    concurrency: Annotated[
        int, typer.Option("--concurrency", help="Parallel block streams (1-32).")
    ] = 3,
    resume: Annotated[
        bool, typer.Option("--resume", help="Continue a prior interrupted transfer.")
    ] = False,
    block_size: Annotated[
        int | None, typer.Option("--block-size", help="Override block size in bytes.")
    ] = None,
    content_type: Annotated[
        str | None, typer.Option("--content-type", help="Content-Type for the destination.")
    ] = None,
    no_progress: Annotated[
        bool, typer.Option("--no-progress", help="Suppress the live progress display.")
    ] = False,
) -> None:
    """Copy SOURCE to DESTINATION, streaming blocks through this host."""
    if not 1 <= concurrency <= 32:
        raise _fail("error: --concurrency must be between 1 and 32", 1)
    if block_size is not None and block_size < 1:
        raise _fail("error: --block-size must be a positive integer", 1)

    try:
        result = copy(
            source,
            destination,
            concurrency=concurrency,
            block_size=block_size,
            content_type=content_type,
            resume=resume,
            progress_factory=_progress_factory(enabled=not no_progress),
        )
    except AuthError as exc:
        raise _fail(str(exc), 2) from exc
    except SourceChangedError as exc:
        raise _fail(f"error: {exc}", 3) from exc
    except FileNotFoundError as exc:
        raise _fail(f"error: source not found: {exc}", 1) from exc
    except ValueError as exc:
        raise _fail(f"error: {exc}", 1) from exc
    except IntegrityError as exc:
        raise _fail(f"integrity check failed: {exc}", 4) from exc
    except Exception as exc:  # noqa: BLE001 - map any transfer failure to a non-zero exit
        raise _fail(f"transfer failed: {exc}", 4) from exc

    typer.secho(
        f"copied {result.source} -> {result.destination} ({result.size} bytes), verified",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()
