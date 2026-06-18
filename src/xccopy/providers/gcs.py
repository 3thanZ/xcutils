"""Google Cloud Storage provider (scheme ``gs``).

Authenticates with Application Default Credentials (``gcloud auth application-default
login``). The destination sink performs an ordered resumable upload.

Resume note (v1): GCS uploads stream in order and the upload session is not persisted across
processes, so GCS-destination resume restarts the upload (``already_done`` is empty). Azure
destinations resume at block granularity. Research D4 records the XML-multipart enhancement
that would add cross-process GCS resume + write-side parallelism.
"""

from __future__ import annotations

import base64
import threading
from collections.abc import Mapping
from typing import Any

from xccopy.blocks import Block
from xccopy.providers.base import BlobProvider, BlockSink, CommitResult, ObjectStat
from xcutils_common.auth import gcp_credentials
from xcutils_common.uri import BlobLocation


def _md5_from_b64(value: str | None) -> str | None:
    if not value:
        return None
    return "md5:" + base64.b64decode(value).hex()


class GcsProvider(BlobProvider):
    scheme = "gs"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client: Any = None

    def _bucket(self, name: str) -> Any:
        from google.cloud import storage

        with self._lock:
            if self._client is None:
                credentials, project = gcp_credentials()
                self._client = storage.Client(project=project, credentials=credentials)
        return self._client.bucket(name)

    def stat(self, location: BlobLocation) -> ObjectStat:
        blob = self._bucket(location.bucket).get_blob(location.key)
        if blob is None:
            raise FileNotFoundError(location.uri)
        return ObjectStat(
            size=blob.size or 0,
            fingerprint=f"generation:{blob.generation}",
            content_type=blob.content_type,
            source_hash=_md5_from_b64(blob.md5_hash),
        )

    def read_block(self, location: BlobLocation, offset: int, length: int) -> bytes:
        blob = self._bucket(location.bucket).blob(location.key)
        # GCS range end is inclusive.
        return bytes(blob.download_as_bytes(start=offset, end=offset + length - 1))

    def open_sink(
        self,
        location: BlobLocation,
        *,
        total_size: int,
        block_size: int,
        content_type: str | None,
        resume_state: Mapping[str, Any] | None,
    ) -> BlockSink:
        blob = self._bucket(location.bucket).blob(location.key)
        return GcsStreamSink(blob, content_type=content_type, total_size=total_size)


class GcsStreamSink(BlockSink):
    requires_ordered = True

    def __init__(self, blob: Any, *, content_type: str | None, total_size: int) -> None:
        self._blob = blob
        self._content_type = content_type or "application/octet-stream"
        self._total = total_size
        self._writer: Any = None

    def already_done(self) -> set[int]:
        return set()  # see module docstring: GCS-destination resume restarts in v1

    def _ensure_writer(self) -> Any:
        if self._writer is None:
            self._writer = self._blob.open("wb", content_type=self._content_type)
        return self._writer

    def stage(self, block: Block, data: bytes) -> None:
        self._ensure_writer().write(data)

    def commit(self, ordered_indices: list[int]) -> CommitResult:
        if self._writer is not None:
            self._writer.close()
        else:  # zero-byte object: no blocks were staged
            self._blob.upload_from_string(b"", content_type=self._content_type)
        self._blob.reload()
        return CommitResult(size=self._blob.size or 0, dest_hash=_md5_from_b64(self._blob.md5_hash))

    def abort(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass

    def resume_state(self) -> dict[str, Any]:
        return {"kind": "gcs-stream"}
