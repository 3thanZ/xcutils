"""Parsing of cross-cloud blob URIs into a normalized location.

Supported schemes:
  - ``gs://<bucket>/<object-path>``                  (Google Cloud Storage)
  - ``az://<account>/<container>/<blob-path>``       (Azure Blob Storage)
  - ``s3://<bucket>/<object-path>``                  (AWS S3, reserved for future use)

A :class:`BlobLocation` is intentionally cloud-neutral; providers interpret the
fields they need. ``container`` is only meaningful for Azure.
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_SCHEMES = ("gs", "az", "s3")


@dataclass(frozen=True)
class BlobLocation:
    """A normalized pointer to an object in some cloud blob store."""

    scheme: str
    #: GCS bucket, Azure storage account, or S3 bucket depending on scheme.
    bucket: str
    #: Path/key of the object within its container/bucket.
    key: str
    #: Azure container name. ``None`` for schemes that do not use containers.
    container: str | None = None

    @property
    def uri(self) -> str:
        if self.scheme == "az":
            return f"az://{self.bucket}/{self.container}/{self.key}"
        return f"{self.scheme}://{self.bucket}/{self.key}"


def parse_blob_uri(uri: str) -> BlobLocation:
    """Parse a blob URI into a :class:`BlobLocation`.

    Raises:
        ValueError: if the scheme is unsupported or the URI is malformed.
    """
    if "://" not in uri:
        raise ValueError(
            f"Not a blob URI: {uri!r}. Expected one of "
            f"{', '.join(s + '://...' for s in SUPPORTED_SCHEMES)}."
        )

    scheme, _, remainder = uri.partition("://")
    scheme = scheme.lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(
            f"Unsupported scheme {scheme!r} in {uri!r}. "
            f"Supported: {', '.join(SUPPORTED_SCHEMES)}."
        )

    if scheme == "az":
        # az://<account>/<container>/<blob-path>
        account, _, rest = remainder.partition("/")
        container, _, key = rest.partition("/")
        if not account or not container or not key:
            raise ValueError(
                f"Azure URI must be az://<account>/<container>/<blob-path>, got {uri!r}."
            )
        return BlobLocation(scheme=scheme, bucket=account, container=container, key=key)

    # gs:// and s3://  ->  <bucket>/<object-path>
    bucket, _, key = remainder.partition("/")
    if not bucket or not key:
        raise ValueError(f"{scheme} URI must be {scheme}://<bucket>/<object-path>, got {uri!r}.")
    return BlobLocation(scheme=scheme, bucket=bucket, key=key)
