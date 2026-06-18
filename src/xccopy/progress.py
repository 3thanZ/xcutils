"""Live progress reporting (FR-014, User Story 4, SC-008).

The engine reports completed-byte deltas through a simple ``advance(n)`` callable, so it
has no hard dependency on the renderer. ``ProgressState`` is a thread-safe counter used in
tests; ``live_progress`` is the rich-backed display used by the CLI.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class ProgressState:
    """Thread-safe byte counter (used by tests and as a headless reporter)."""

    def __init__(self, total: int) -> None:
        self.total = total
        self._completed = 0
        self._lock = threading.Lock()

    def advance(self, n_bytes: int) -> None:
        with self._lock:
            self._completed += n_bytes

    @property
    def completed(self) -> int:
        with self._lock:
            return self._completed


@contextmanager
def live_progress(
    total: int, label: str, *, enabled: bool = True
) -> Iterator[Callable[[int], None]]:
    """Yield an ``advance(n)`` callable backed by a live rich progress bar.

    When disabled (or for a zero-byte object) yields a no-op so callers need no branching.
    """
    if not enabled or total == 0:
        yield lambda _n: None
        return

    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(label, total=total)
        # Progress.update is internally locked, so this is safe to call from worker threads.
        yield lambda n: progress.update(task, advance=n)
