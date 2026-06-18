"""The ordered engine path must stage blocks in index order despite parallel reads."""

from __future__ import annotations

import random
import time

from fakes import FakeCloud, FakeProvider

from xccopy.blocks import plan_blocks
from xccopy.engine import run_transfer
from xccopy.providers.base import Block, BlockSink, CommitResult
from xcutils_common.uri import parse_blob_uri

SRC = parse_blob_uri("gs://bucket/src")
DST = parse_blob_uri("gs://bucket/dst")


class OrderRecordingProvider(FakeProvider):
    """Reads return after a jittered delay, so completion order != index order."""

    def read_block(self, location: object, offset: int, length: int) -> bytes:  # type: ignore[override]
        time.sleep(random.uniform(0, 0.005))
        return super().read_block(location, offset, length)  # type: ignore[arg-type]


class OrderAssertingSink(BlockSink):
    requires_ordered = True

    def __init__(self) -> None:
        self.staged_order: list[int] = []
        self._data: dict[int, bytes] = {}

    def already_done(self) -> set[int]:
        return set()

    def stage(self, block: Block, data: bytes) -> None:
        self.staged_order.append(block.index)
        self._data[block.index] = data

    def commit(self, ordered_indices: list[int]) -> CommitResult:
        blob = b"".join(self._data[i] for i in ordered_indices)
        return CommitResult(size=len(blob), dest_hash=None)

    def abort(self) -> None:
        pass

    def resume_state(self) -> dict[str, object]:
        return {}


def test_ordered_sink_receives_blocks_in_index_order() -> None:
    cloud = FakeCloud()
    cloud.put(SRC, bytes(range(256)) * 80)  # ~20 KB
    provider = OrderRecordingProvider(cloud, ordered=True)
    plan = plan_blocks(len(cloud.objects[SRC.uri]), 1024)
    sink = OrderAssertingSink()

    run_transfer(source=SRC, source_provider=provider, sink=sink, plan=plan, concurrency=8)

    assert sink.staged_order == list(range(plan.count))
