"""Azure Blob Storage provider (scheme ``az``).

Authenticates with the local Azure CLI session via ``AzureCliCredential``. The destination
sink uses block blobs: ``stage_block`` (parallel, unordered) then ``commit_block_list``.
"""

from __future__ import annotations

import base64
import threading
from collections.abc import Mapping
from typing import Any

from xccopy.blocks import Block
from xccopy.providers.base import BlobProvider, BlockSink, CommitResult, ObjectStat
from xcutils_common.auth import azure_cli_credential
from xcutils_common.uri import BlobLocation


def block_id(index: int) -> str:
    """Stable, equal-length, base64 block id for a block index (Azure requires equal length)."""
    return base64.b64encode(b"xccopy-%032d" % index).decode("ascii")


def _md5_hex(value: bytes | bytearray | None) -> str | None:
    if not value:
        return None
    return "md5:" + bytes(value).hex()


class AzureBlobProvider(BlobProvider):
    scheme = "az"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._credential: Any = None
        self._services: dict[str, Any] = {}

    def _service(self, account: str) -> Any:
        from azure.storage.blob import BlobServiceClient

        with self._lock:
            if self._credential is None:
                self._credential = azure_cli_credential()
            service = self._services.get(account)
            if service is None:
                service = BlobServiceClient(
                    account_url=f"https://{account}.blob.core.windows.net",
                    credential=self._credential,
                )
                self._services[account] = service
            return service

    def _blob_client(self, location: BlobLocation) -> Any:
        assert location.container is not None, "az:// locations always have a container"
        return self._service(location.bucket).get_blob_client(
            container=location.container, blob=location.key
        )

    def stat(self, location: BlobLocation) -> ObjectStat:
        from azure.core.exceptions import ResourceNotFoundError

        client = self._blob_client(location)
        try:
            props = client.get_blob_properties()
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(location.uri) from exc
        settings = props.content_settings
        return ObjectStat(
            size=props.size,
            fingerprint=f"etag:{props.etag}",
            content_type=settings.content_type if settings else None,
            source_hash=_md5_hex(settings.content_md5) if settings else None,
        )

    def read_block(self, location: BlobLocation, offset: int, length: int) -> bytes:
        downloader = self._blob_client(location).download_blob(offset=offset, length=length)
        return bytes(downloader.readall())

    def open_sink(
        self,
        location: BlobLocation,
        *,
        total_size: int,
        block_size: int,
        content_type: str | None,
        resume_state: Mapping[str, Any] | None,
    ) -> BlockSink:
        return AzureBlockBlobSink(
            self._blob_client(location), content_type=content_type, resume_state=resume_state
        )


class AzureBlockBlobSink(BlockSink):
    requires_ordered = False

    def __init__(
        self,
        client: Any,
        *,
        content_type: str | None,
        resume_state: Mapping[str, Any] | None,
    ) -> None:
        self._client = client
        self._content_type = content_type
        self._lock = threading.Lock()
        self._block_ids: dict[int, str] = {}
        if resume_state:
            self._block_ids = {
                int(k): v for k, v in resume_state.get("block_ids", {}).items()
            }

    def already_done(self) -> set[int]:
        return set(self._block_ids)

    def stage(self, block: Block, data: bytes) -> None:
        bid = block_id(block.index)
        # validate_content=True has Azure verify the block's MD5 on receipt (FR-013).
        self._client.stage_block(block_id=bid, data=data, length=len(data), validate_content=True)
        with self._lock:
            self._block_ids[block.index] = bid

    def commit(self, ordered_indices: list[int]) -> CommitResult:
        from azure.storage.blob import BlobBlock, ContentSettings

        block_list = [BlobBlock(block_id=self._block_ids[i]) for i in ordered_indices]
        settings = ContentSettings(content_type=self._content_type) if self._content_type else None
        self._client.commit_block_list(block_list, content_settings=settings)
        props = self._client.get_blob_properties()
        cs = props.content_settings
        return CommitResult(size=props.size, dest_hash=_md5_hex(cs.content_md5) if cs else None)

    def abort(self) -> None:
        pass  # uncommitted staged blocks expire server-side; kept meanwhile for --resume

    def resume_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "kind": "azure-block-blob",
                "block_ids": {str(k): v for k, v in self._block_ids.items()},
            }
