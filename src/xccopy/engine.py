"""The cloud-agnostic block-transfer engine.

Fetches source byte ranges in parallel and streams them into a destination
:class:`BlockSink`. Unordered sinks (Azure block staging) accept blocks concurrently in
any order; ordered sinks (GCS resumable upload) receive blocks in index order, fed from a
bounded reorder buffer so the host's memory stays capped at roughly
``(concurrency + REORDER_WINDOW) × block_size`` regardless of object size.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from xccopy.blocks import Block, BlockPlan
from xccopy.providers.base import BlobProvider, BlockSink, CommitResult
from xcutils_common.uri import BlobLocation

#: Extra blocks the ordered path may read ahead of the stage cursor.
REORDER_WINDOW = 4

ProgressCallback = Callable[[int], None]
BlockDoneCallback = Callable[[int], None]


def run_transfer(
    *,
    source: BlobLocation,
    source_provider: BlobProvider,
    sink: BlockSink,
    plan: BlockPlan,
    concurrency: int = 3,
    on_progress: ProgressCallback | None = None,
    on_block_done: BlockDoneCallback | None = None,
) -> CommitResult:
    """Stream ``plan``'s blocks from ``source`` into ``sink`` and commit.

    Blocks already present in ``sink.already_done()`` are skipped (resume). ``on_progress``
    receives byte deltas (including resumed bytes up front); ``on_block_done`` receives each
    block index after it is durably staged and is called serially.
    """
    done = sink.already_done()
    todo = [b for b in plan.blocks if b.index not in done]

    if on_progress is not None and done:
        resumed = sum(b.length for b in plan.blocks if b.index in done)
        if resumed:
            on_progress(resumed)

    cb_lock = threading.Lock()

    def block_done(index: int, n_bytes: int) -> None:
        if on_progress is not None:
            on_progress(n_bytes)
        if on_block_done is not None:
            with cb_lock:
                on_block_done(index)

    if todo:
        if sink.requires_ordered:
            _run_ordered(source, source_provider, sink, todo, concurrency, block_done)
        else:
            _run_unordered(source, source_provider, sink, todo, concurrency, block_done)

    return sink.commit([b.index for b in plan.blocks])


def _run_unordered(
    source: BlobLocation,
    provider: BlobProvider,
    sink: BlockSink,
    todo: list[Block],
    concurrency: int,
    block_done: Callable[[int, int], None],
) -> None:
    def stage_one(block: Block) -> None:
        data = provider.read_block(source, block.offset, block.length)
        sink.stage(block, data)
        block_done(block.index, len(data))

    # The pool runs at most `concurrency` reads at once, so live data is bounded.
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(stage_one, b) for b in todo]
        for future in as_completed(futures):
            future.result()  # re-raise the first failure


def _run_ordered(
    source: BlobLocation,
    provider: BlobProvider,
    sink: BlockSink,
    todo: list[Block],
    concurrency: int,
    block_done: Callable[[int, int], None],
) -> None:
    max_outstanding = concurrency + REORDER_WINDOW
    sem = threading.Semaphore(max_outstanding)  # caps blocks held in the reorder buffer
    cond = threading.Condition()
    buffer: dict[int, bytes] = {}
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader(block: Block) -> None:
        while not sem.acquire(timeout=0.1):
            if stop.is_set():
                return
        if stop.is_set():
            return
        try:
            data = provider.read_block(source, block.offset, block.length)
        except BaseException as exc:  # noqa: BLE001 - surfaced to the consumer
            with cond:
                errors.append(exc)
                cond.notify_all()
            return
        with cond:
            buffer[block.index] = data
            cond.notify_all()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for block in todo:
            pool.submit(reader, block)
        try:
            for block in todo:
                with cond:
                    while block.index not in buffer and not errors:
                        cond.wait()
                    if errors:
                        raise errors[0]
                    data = buffer.pop(block.index)
                sink.stage(block, data)
                sem.release()
                block_done(block.index, len(data))
        finally:
            # Unblock any readers still waiting on the semaphore so the pool can shut down.
            stop.set()
            for _ in range(max_outstanding + len(todo)):
                sem.release()
