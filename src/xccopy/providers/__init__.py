"""Provider registry, keyed by URI scheme.

Register a new cloud by adding its provider class here; utilities resolve
providers through :func:`get_provider` and never import a cloud SDK directly.
"""

from __future__ import annotations

from xccopy.providers.azure import AzureBlobProvider
from xccopy.providers.base import BlobProvider
from xccopy.providers.gcs import GcsProvider

_PROVIDERS: dict[str, type[BlobProvider]] = {
    GcsProvider.scheme: GcsProvider,
    AzureBlobProvider.scheme: AzureBlobProvider,
}


def get_provider(scheme: str) -> BlobProvider:
    """Return a provider instance for ``scheme`` (e.g. ``"gs"``, ``"az"``)."""
    try:
        return _PROVIDERS[scheme]()
    except KeyError:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"No provider for scheme {scheme!r}. Supported: {supported}."
        ) from None


__all__ = ["BlobProvider", "get_provider"]
