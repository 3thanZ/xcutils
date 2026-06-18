"""Local, metadata-only resume state (FR-011, FR-022).

One JSON file per transfer under ``$XDG_STATE_HOME/xccopy`` (default ``~/.local/state``),
named by a hash of the source+destination URIs. Contains no object bytes and no credentials.
See contracts/checkpoint-schema.md.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(Path.home(), ".local", "state")
    return Path(base) / "xccopy"


def path_for(source_uri: str, destination_uri: str) -> Path:
    digest = hashlib.sha256(f"{source_uri}\0{destination_uri}".encode()).hexdigest()
    return _state_dir() / f"{digest}.json"


def load(source_uri: str, destination_uri: str) -> dict[str, Any] | None:
    """Load a usable checkpoint, or ``None`` if absent, unreadable, or a future version."""
    file = path_for(source_uri, destination_uri)
    try:
        raw = file.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if data.get("version") != SCHEMA_VERSION:
        return None
    if data.get("source_uri") != source_uri or data.get("destination_uri") != destination_uri:
        return None
    return data


def new_record(
    source_uri: str,
    destination_uri: str,
    *,
    source_fingerprint: str,
    block_size: int,
    total_size: int,
) -> dict[str, Any]:
    now = _now()
    return {
        "version": SCHEMA_VERSION,
        "source_uri": source_uri,
        "destination_uri": destination_uri,
        "source_fingerprint": source_fingerprint,
        "block_size": block_size,
        "total_size": total_size,
        "completed_blocks": [],
        "sink_state": {},
        "created_at": now,
        "updated_at": now,
    }


def save(record: dict[str, Any]) -> None:
    """Atomically persist ``record`` with restrictive permissions."""
    directory = _state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    file = path_for(record["source_uri"], record["destination_uri"])
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        os.chmod(tmp, 0o600)
        os.replace(tmp, file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def mark_block(record: dict[str, Any], index: int, sink_state: dict[str, Any]) -> None:
    """Record a completed block and the sink's resume state, then persist."""
    completed: list[int] = record["completed_blocks"]
    if index not in completed:
        completed.append(index)
    record["sink_state"] = sink_state
    record["updated_at"] = _now()
    save(record)


def delete(source_uri: str, destination_uri: str) -> None:
    with contextlib.suppress(OSError):
        path_for(source_uri, destination_uri).unlink()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
