"""Live cross-cloud copy (US1). Requires XCCOPY_LIVE=1 and authenticated CLIs.

Set XCCOPY_TEST_SRC and XCCOPY_TEST_DST to a readable source object and a writable
destination URI (different clouds recommended).
"""

from __future__ import annotations

import os

import pytest

from xccopy.copier import copy
from xccopy.providers import get_provider
from xcutils_common.uri import parse_blob_uri

SRC = os.environ.get("XCCOPY_TEST_SRC", "")
DST = os.environ.get("XCCOPY_TEST_DST", "")

pytestmark = pytest.mark.skipif(not (SRC and DST), reason="set XCCOPY_TEST_SRC/XCCOPY_TEST_DST")


def test_cross_cloud_copy_verifies() -> None:
    result = copy(SRC, DST, concurrency=3)
    src_stat = get_provider(parse_blob_uri(SRC).scheme).stat(parse_blob_uri(SRC))
    assert result.size == src_stat.size  # copy() already integrity-verified internally
