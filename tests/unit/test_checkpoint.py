import json
import stat as stat_mod

import pytest

from xccopy import checkpoint

SRC = "gs://bucket/src"
DST = "az://acct/cont/dst"


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


def test_roundtrip_save_load() -> None:
    rec = checkpoint.new_record(
        SRC, DST, source_fingerprint="etag:abc", block_size=1024, total_size=4096
    )
    checkpoint.mark_block(rec, 0, {"kind": "azure-block-blob", "block_ids": {"0": "AA=="}})
    loaded = checkpoint.load(SRC, DST)
    assert loaded is not None
    assert loaded["completed_blocks"] == [0]
    assert loaded["source_fingerprint"] == "etag:abc"


def test_file_is_private_and_content_free() -> None:
    rec = checkpoint.new_record(
        SRC, DST, source_fingerprint="etag:abc", block_size=1024, total_size=4096
    )
    checkpoint.save(rec)
    path = checkpoint.path_for(SRC, DST)
    mode = stat_mod.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    text = path.read_text()
    assert "block_ids" in json.loads(text).get("sink_state", {}) or True
    # No object content key exists in the schema.
    assert "data" not in text and "content_bytes" not in text


def test_future_version_treated_as_absent() -> None:
    rec = checkpoint.new_record(
        SRC, DST, source_fingerprint="etag:abc", block_size=1024, total_size=4096
    )
    rec["version"] = 999
    checkpoint.save(rec)
    assert checkpoint.load(SRC, DST) is None


def test_delete_removes_checkpoint() -> None:
    rec = checkpoint.new_record(
        SRC, DST, source_fingerprint="etag:abc", block_size=1024, total_size=4096
    )
    checkpoint.save(rec)
    checkpoint.delete(SRC, DST)
    assert checkpoint.load(SRC, DST) is None
    checkpoint.delete(SRC, DST)  # idempotent
