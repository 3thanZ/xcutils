"""Shared building blocks for xcutils utilities.

This package holds cross-cutting concerns used by every utility: cloud
authentication (CLI-session based, never key based) and blob URI parsing.
"""

from xcutils_common.uri import BlobLocation, parse_blob_uri

__all__ = ["BlobLocation", "parse_blob_uri"]
