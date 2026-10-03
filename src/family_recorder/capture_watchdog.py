from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable

LOGGER = logging.getLogger(__name__)


def capture_timeout_seconds(chunk_seconds: float) -> float:
    return max(90.0, chunk_seconds * 3)


class CaptureWatchdog:
    """Escape native audio hangs so the service manager can start fresh.

    PortAudio can block forever after a CoreAudio device disappears. Retrying
    device discovery in the same process can also retain an obsolete device
    list. Only completed captures renew the deadline; retry attempts do not.
    """

    def __init__(
        self,
        timeout_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Capture timeout must be positive")
        self.timeout_seconds = timeout_seconds
        self._clock = clock
        self._deadline: float | None = None
        self._stage = "idle"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._watch, name="familyrecorder-capture-watchdog", daemon=True
        )

    def __enter__(self) -> CaptureWatchdog:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def arm(self, stage: str) -> None:
        with self._lock:
            self._stage = stage
            if self._deadline is None:
                self._deadline = self._clock() + self.timeout_seconds

    def progress(self) -> None:
        with self._lock:
            self._deadline = self._clock() + self.timeout_seconds

    def suspend(self) -> None:
        with self._lock:
            self._deadline = None

    def _expired_stage(self) -> str | None:
        with self._lock:
            if self._deadline is not None and self._clock() >= self._deadline:
                return self._stage
        return None

    def _watch(self) -> None:
        while not self._stop.wait(min(1.0, self.timeout_seconds / 4)):
            stage = self._expired_stage()
            if stage is None:
                continue
            LOGGER.critical(
                "No completed audio capture for %.1f seconds (stage=%s, pid=%d); "
                "exiting with status 75 so launchd can reconnect the microphone",
                self.timeout_seconds,
                stage,
                os.getpid(),
            )
            # Raising in this thread cannot interrupt a blocked C audio read.
            # launchd KeepAlive restarts the app wrapper on this nonzero exit.
            os._exit(75)
