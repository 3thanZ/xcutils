"""In-memory fakes implementing the provider/sink contract, for offline tests.

``FakeCloud`` models a blob store with committed objects plus a server-side staging
area (like Azure uncommitted blocks) so resume across sink instances is testable.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Mapping
from typing import Any

from xccopy.blocks import Block
from xccopy.providers.base import BlobProvider, BlockSink, CommitResult, ObjectStat
from xcutils_common.uri import BlobLocation


def _md5(data: bytes) -> str:
    return "md5:" + hashlib.md5(data).hexdigest()


class FakeCloud:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.staging: dict[str, dict[int, bytes]] = {}
        self.read_calls: list[tuple[str, int, int]] = []
        self.lock = threading.Lock()

    def put(self, location: BlobLocation, data: bytes) -> None:
        self.objects[location.uri] = data


class FakeProvider(BlobProvider):
    def __init__(self, cloud: FakeCloud, scheme: str = "gs", ordered: bool = False) -> None:
        self.cloud = cloud
        self.scheme = scheme
        self._ordered = ordered

    def stat(self, location: BlobLocation) -> ObjectStat:
        try:
            data = self.cloud.objects[location.uri]
        except KeyError as exc:
            raise FileNotFoundError(location.uri) from exc
        return ObjectStat(
            size=len(data),
            fingerprint=f"etag:{_md5(data)}",
            content_type="application/octet-stream",
            source_hash=_md5(data),
        )

    def read_block(self, location: BlobLocation, offset: int, length: int) -> bytes:
        with self.cloud.lock:
            self.cloud.read_calls.append((location.uri, offset, length))
        return self.cloud.objects[location.uri][offset : offset + length]

    def open_sink(
        self,
        location: BlobLocation,
        *,
        total_size: int,
        block_size: int,
        content_type: str | None,
        resume_state: Mapping[str, Any] | None,
    ) -> BlockSink:
        return FakeSink(self.cloud, location, ordered=self._ordered, resume_state=resume_state)


class FakeSink(BlockSink):
    def __init__(
        self,
        cloud: FakeCloud,
        location: BlobLocation,
        *,
        ordered: bool,
        resume_state: Mapping[str, Any] | None,
    ) -> None:
        self.requires_ordered = ordered
        self._cloud = cloud
        self._uri = location.uri
        self._lock = threading.Lock()
        self._last_index = -1
        if resume_state is None:
            cloud.staging[self._uri] = {}  # fresh transfer discards prior staging
        else:
            cloud.staging.setdefault(self._uri, {})

    def already_done(self) -> set[int]:
        return set(self._cloud.staging.get(self._uri, {}))

    def stage(self, block: Block, data: bytes) -> None:
        if self.requires_ordered:
            assert block.index == self._last_index + 1, "ordered sink got out-of-order block"
            self._last_index = block.index
        with self._lock:
            self._cloud.staging.setdefault(self._uri, {})[block.index] = bytes(data)

    def commit(self, ordered_indices: list[int]) -> CommitResult:
        staged = self._cloud.staging.get(self._uri, {})
        assembled = b"".join(staged[i] for i in ordered_indices)
        self._cloud.objects[self._uri] = assembled
        self._cloud.staging.pop(self._uri, None)
        return CommitResult(size=len(assembled), dest_hash=_md5(assembled))

    def abort(self) -> None:
        pass

    def resume_state(self) -> dict[str, Any]:
        return {"kind": "fake", "staged": sorted(self._cloud.staging.get(self._uri, {}))}
