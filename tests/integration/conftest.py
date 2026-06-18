"""Integration-test gating.

Live tests touch real cloud blob stores and require authenticated CLI sessions.
They run only when ``XCCOPY_LIVE=1``; otherwise every test in this directory is
skipped, so the default ``pytest`` run stays fully offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

LIVE = os.environ.get("XCCOPY_LIVE") == "1"
_INTEGRATION_DIR = Path(__file__).parent


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if LIVE:
        return
    skip_live = pytest.mark.skip(reason="set XCCOPY_LIVE=1 to run live cloud integration tests")
    # This hook sees ALL collected items, so only skip those under tests/integration/.
    for item in items:
        if _INTEGRATION_DIR in Path(str(item.fspath)).parents:
            item.add_marker(skip_live)
