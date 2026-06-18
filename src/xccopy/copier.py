"""Orchestrates a single resumable, integrity-verified, streaming blob copy."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass

from xccopy import checkpoint
from xccopy.blocks import plan_blocks
from xccopy.engine import run_transfer
from xccopy.providers import get_provider
from xccopy.verify import verify
from xcutils_common.uri import parse_blob_uri

#: Given (total_bytes, label), returns a context manager yielding an ``advance(n)`` callable.
ProgressFactory = Callable[[int, str], AbstractContextManager["Callable[[int], None] | None"]]


class SourceChangedError(RuntimeError):
    """Raised when --resume is requested but the source changed since interruption (FR-012)."""


@dataclass(frozen=True)
class CopyResult:
    source: str
    destination: str
    size: int


def copy(
    source_uri: str,
    destination_uri: str,
    *,
    concurrency: int = 3,
    block_size: int | None = None,
    content_type: str | None = None,
    resume: bool = False,
    progress_factory: ProgressFactory | None = None,
) -> CopyResult:
    """Stream the object at ``source_uri`` to ``destination_uri``.

    Bytes flow source → host → destination in bounded blocks; the whole object is never
    assembled on the host. On success the destination is integrity-verified and any
    checkpoint cleared.
    """
    src = parse_blob_uri(source_uri)
    dst = parse_blob_uri(destination_uri)
    src_provider = get_provider(src.scheme)
    dst_provider = get_provider(dst.scheme)

    stat = src_provider.stat(src)  # FileNotFoundError if the source is missing

    record = checkpoint.load(source_uri, destination_uri) if resume else None
    if resume and record is not None:
        if record["source_fingerprint"] != stat.fingerprint:
            raise SourceChangedError(
                "source changed since the interrupted transfer; "
                "re-run without --resume to start fresh"
            )
        block_size = record["block_size"]
        sink_resume_state = record.get("sink_state") or None
    else:
        # Fresh run: discard any stale checkpoint and overwrite the destination (FR-008/FR-010).
        checkpoint.delete(source_uri, destination_uri)
        record = None
        sink_resume_state = None

    plan = plan_blocks(stat.size, block_size)

    sink = dst_provider.open_sink(
        dst,
        total_size=stat.size,
        block_size=plan.block_size,
        content_type=content_type or stat.content_type,
        resume_state=sink_resume_state,
    )

    if record is None:
        record = checkpoint.new_record(
            source_uri,
            destination_uri,
            source_fingerprint=stat.fingerprint,
            block_size=plan.block_size,
            total_size=stat.size,
        )

    def on_block_done(index: int) -> None:
        checkpoint.mark_block(record, index, sink.resume_state())

    label = f"{src.uri} -> {dst.uri}"
    ctx: AbstractContextManager[Callable[[int], None] | None] = (
        progress_factory(stat.size, label) if progress_factory is not None else nullcontext(None)
    )

    try:
        with ctx as advance:
            result = run_transfer(
                source=src,
                source_provider=src_provider,
                sink=sink,
                plan=plan,
                concurrency=concurrency,
                on_progress=advance,
                on_block_done=on_block_done,
            )
    except BaseException:
        sink.abort()
        raise

    verify(stat, result)
    checkpoint.delete(source_uri, destination_uri)
    return CopyResult(source=src.uri, destination=dst.uri, size=result.size)
