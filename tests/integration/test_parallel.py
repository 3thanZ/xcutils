"""Live parallel-speedup check (US2, SC-002). Requires XCCOPY_LIVE=1.

Best run against a large (>=10 GB) object with an Azure destination. Marked slow.
"""

from __future__ import annotations

import os
import time

import pytest

from xccopy.copier import copy

SRC = os.environ.get("XCCOPY_TEST_SRC", "")
DST = os.environ.get("XCCOPY_TEST_DST", "")

pytestmark = pytest.mark.skipif(not (SRC and DST), reason="set XCCOPY_TEST_SRC/XCCOPY_TEST_DST")


@pytest.mark.slow
def test_parallel_is_faster_than_serial() -> None:
    t0 = time.monotonic()
    copy(SRC, DST, concurrency=1)
    serial = time.monotonic() - t0

    t0 = time.monotonic()
    copy(SRC, DST, concurrency=3)
    parallel = time.monotonic() - t0

    # SC-002: >=40% faster for a sufficiently large object on a parallel-friendly destination.
    assert parallel <= serial * 0.6, f"serial={serial:.1f}s parallel={parallel:.1f}s"
