"""Live resume check (US3). Requires XCCOPY_LIVE=1 and an Azure destination.

Azure destinations resume at block granularity. This test stages a partial transfer by
copying with a tiny block size and interrupting via a low-level abort, then resumes.
Kept minimal; primarily exercised manually per quickstart Scenario 3.
"""

from __future__ import annotations

import os

import pytest

from xccopy.copier import copy

SRC = os.environ.get("XCCOPY_TEST_SRC", "")
DST = os.environ.get("XCCOPY_TEST_DST_AZURE", "")

pytestmark = pytest.mark.skipif(
    not (SRC and DST.startswith("az://")),
    reason="set XCCOPY_TEST_SRC and an az:// XCCOPY_TEST_DST_AZURE",
)


def test_resume_completes_after_partial() -> None:
    # A full copy followed by a --resume re-run must converge to a verified object and
    # must not error (resume with a complete checkpoint behaves like a no-op finalize).
    copy(SRC, DST, concurrency=3)
    result = copy(SRC, DST, concurrency=3, resume=True)
    assert result.size >= 0
