"""Conformance tests for the BlobProvider/BlockSink contract, via in-memory fakes."""

from __future__ import annotations

import json

import pytest
from fakes import FakeCloud, FakeProvider

from xccopy.blocks import plan_blocks
from xccopy.engine import run_transfer
from xccopy.verify import verify
from xcutils_common.uri import parse_blob_uri

SRC = parse_blob_uri("gs://bucket/source")
DST = parse_blob_uri("gs://bucket/dest")


def _payload(size: int) -> bytes:
    return bytes((i * 7 + 3) % 256 for i in range(size))


@pytest.mark.parametrize("ordered", [False, True])
@pytest.mark.parametrize("size,block_size", [(0, 1024), (5, 1024), (1000, 256), (8192, 1024)])
def test_roundtrip_matches_source(ordered: bool, size: int, block_size: int) -> None:
    cloud = FakeCloud()
    cloud.put(SRC, _payload(size))
    provider = FakeProvider(cloud, ordered=ordered)

    stat = provider.stat(SRC)
    plan = plan_blocks(stat.size, block_size)
    sink = provider.open_sink(
        DST, total_size=stat.size, block_size=plan.block_size, content_type=None, resume_state=None
    )
    result = run_transfer(
        source=SRC, source_provider=provider, sink=sink, plan=plan, concurrency=4
    )

    verify(stat, result)  # raises on size/hash mismatch
    assert cloud.objects[DST.uri] == cloud.objects[SRC.uri]


def test_resume_skips_completed_blocks() -> None:
    cloud = FakeCloud()
    cloud.put(SRC, _payload(4000))
    provider = FakeProvider(cloud, ordered=False)
    stat = provider.stat(SRC)
    plan = plan_blocks(stat.size, 1000)  # 4 blocks

    # Stage the first two blocks, then capture resume state (as a checkpoint would).
    sink1 = provider.open_sink(
        DST, total_size=stat.size, block_size=1000, content_type=None, resume_state=None
    )
    sink1.stage(plan.blocks[0], cloud.objects[SRC.uri][0:1000])
    sink1.stage(plan.blocks[1], cloud.objects[SRC.uri][1000:2000])
    state = sink1.resume_state()

    cloud.read_calls.clear()
    sink2 = provider.open_sink(
        DST, total_size=stat.size, block_size=1000, content_type=None, resume_state=state
    )
    result = run_transfer(
        source=SRC, source_provider=provider, sink=sink2, plan=plan, concurrency=2
    )

    verify(stat, result)
    assert cloud.objects[DST.uri] == cloud.objects[SRC.uri]
    # Only the two missing blocks were re-read.
    assert {offset for _, offset, _ in cloud.read_calls} == {2000, 3000}


def test_resume_state_is_json_serializable_and_content_free() -> None:
    cloud = FakeCloud()
    cloud.put(SRC, _payload(2000))
    provider = FakeProvider(cloud)
    plan = plan_blocks(2000, 1000)
    sink = provider.open_sink(
        DST, total_size=2000, block_size=1000, content_type=None, resume_state=None
    )
    sink.stage(plan.blocks[0], cloud.objects[SRC.uri][0:1000])

    encoded = json.dumps(sink.resume_state())  # must not raise
    assert "source" not in encoded or "bytes" not in encoded
    assert cloud.objects[SRC.uri][0:10].decode("latin-1") not in encoded


def test_missing_source_raises() -> None:
    provider = FakeProvider(FakeCloud())
    with pytest.raises(FileNotFoundError):
        provider.stat(SRC)
