"""copier.copy resume behavior: skip completed blocks, refuse on changed source."""

from __future__ import annotations

import pytest
from fakes import FakeCloud, FakeProvider

from xccopy import checkpoint, copier
from xcutils_common.uri import parse_blob_uri

SRC = "gs://bucket/src"
DST = "gs://bucket/dst"


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


@pytest.fixture
def wired_cloud(monkeypatch):  # type: ignore[no-untyped-def]
    cloud = FakeCloud()
    provider = FakeProvider(cloud, ordered=False)
    monkeypatch.setattr(copier, "get_provider", lambda scheme: provider)
    return cloud


def test_resume_refused_when_source_changed(wired_cloud: FakeCloud) -> None:
    wired_cloud.put(parse_blob_uri(SRC), b"original-data" * 1000)
    # Leave a checkpoint whose fingerprint will not match the (changed) source.
    rec = checkpoint.new_record(
        SRC, DST, source_fingerprint="etag:stale", block_size=4096, total_size=13000
    )
    checkpoint.save(rec)

    with pytest.raises(copier.SourceChangedError):
        copier.copy(SRC, DST, resume=True)


def test_fresh_run_overwrites_and_clears_checkpoint(wired_cloud: FakeCloud) -> None:
    wired_cloud.put(parse_blob_uri(SRC), b"hello world" * 500)
    checkpoint.save(
        checkpoint.new_record(
            SRC, DST, source_fingerprint="etag:stale", block_size=4096, total_size=1
        )
    )

    result = copier.copy(SRC, DST, resume=False)  # ignores stale checkpoint

    src_uri, dst_uri = parse_blob_uri(SRC).uri, parse_blob_uri(DST).uri
    assert result.size == len(wired_cloud.objects[src_uri])
    assert wired_cloud.objects[dst_uri] == wired_cloud.objects[src_uri]
    assert checkpoint.load(SRC, DST) is None  # cleared on success


def test_successful_copy_verifies_and_clears(wired_cloud: FakeCloud) -> None:
    wired_cloud.put(parse_blob_uri(SRC), b"x" * 10000)
    result = copier.copy(SRC, DST, concurrency=4, block_size=1024)
    assert result.size == 10000
    assert checkpoint.load(SRC, DST) is None
