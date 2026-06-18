"""The provider contract every cloud blob store implements.

A :class:`BlobProvider` exposes ``stat`` + ranged ``read_block`` for the source side and
``open_sink`` for the destination side. A :class:`BlockSink` accepts blocks (ordered or
not) and commits them into a finished object. Utilities depend only on these abstractions
(constitution principle IV); cloud SDKs live in the concrete providers.
"""

from __future__ import annotations

import abc
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from xccopy.blocks import Block
from xcutils_common.uri import BlobLocation


@dataclass(frozen=True)
class ObjectStat:
    """Source object metadata used for planning, fingerprinting, and integrity."""

    size: int
    #: Source identity for safe resume — Azure ETag / GCS generation.
    fingerprint: str
    content_type: str | None = None
    #: Server-reported content hash (algorithm-tagged, e.g. "md5:..."), if available.
    source_hash: str | None = None


@dataclass(frozen=True)
class CommitResult:
    """Outcome of finalizing the destination object."""

    size: int
    #: Destination content hash (algorithm-tagged), if the service reports one.
    dest_hash: str | None = None


class BlockSink(abc.ABC):
    """Destination-side accumulator that blocks are streamed into."""

    #: True if blocks must be staged in ascending index order (e.g. GCS resumable upload).
    requires_ordered: bool

    @abc.abstractmethod
    def already_done(self) -> set[int]:
        """Block indices already persisted server-side (for resume); empty when fresh."""

    @abc.abstractmethod
    def stage(self, block: Block, data: bytes) -> None:
        """Persist one block server-side (with a per-block integrity check where supported)."""

    @abc.abstractmethod
    def commit(self, ordered_indices: list[int]) -> CommitResult:
        """Finalize the object from its blocks in index order."""

    @abc.abstractmethod
    def abort(self) -> None:
        """Release engine-side resources; server-side staged state may persist for resume."""

    @abc.abstractmethod
    def resume_state(self) -> dict[str, Any]:
        """JSON-serializable resume metadata (no object bytes, no credentials)."""


class BlobProvider(abc.ABC):
    """Streaming block-level access to one cloud's blob store."""

    scheme: str

    @abc.abstractmethod
    def stat(self, location: BlobLocation) -> ObjectStat:
        """Return source metadata. Raise ``FileNotFoundError`` if the object is absent."""

    @abc.abstractmethod
    def read_block(self, location: BlobLocation, offset: int, length: int) -> bytes:
        """Read exactly ``[offset, offset+length)``. Must be thread-safe."""

    @abc.abstractmethod
    def open_sink(
        self,
        location: BlobLocation,
        *,
        total_size: int,
        block_size: int,
        content_type: str | None,
        resume_state: Mapping[str, Any] | None,
    ) -> BlockSink:
        """Create or resume a destination sink for ``location``."""

    # Optional convenience: whole-object streaming read. Not used by the block engine,
    # kept for simple callers and ad-hoc use.
    def open_read(
        self, location: BlobLocation, chunk_size: int = 8 * 1024 * 1024
    ) -> AbstractContextManager[Iterator[bytes]]:  # pragma: no cover - optional helper
        raise NotImplementedError
