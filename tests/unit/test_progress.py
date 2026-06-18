import threading

from xccopy.progress import ProgressState, live_progress


def test_progress_state_is_thread_safe() -> None:
    state = ProgressState(total=10_000)

    def worker() -> None:
        for _ in range(1000):
            state.advance(1)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state.completed == 10_000


def test_live_progress_disabled_yields_noop() -> None:
    with live_progress(1000, "x", enabled=False) as advance:
        advance(500)  # must not raise


def test_live_progress_zero_total_yields_noop() -> None:
    with live_progress(0, "x", enabled=True) as advance:
        advance(0)
