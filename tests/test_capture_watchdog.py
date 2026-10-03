import os
import subprocess
import sys
from pathlib import Path

import pytest

from family_recorder.capture_watchdog import CaptureWatchdog, capture_timeout_seconds


def test_only_completed_captures_extend_deadline_and_pause_disarms() -> None:
    now = 0.0
    watchdog = CaptureWatchdog(90, clock=lambda: now)
    watchdog.arm("opening microphone")
    now = 80
    watchdog.arm("waiting to reconnect microphone")
    now = 91
    assert watchdog._expired_stage() == "waiting to reconnect microphone"

    watchdog.progress()
    now = 150
    assert watchdog._expired_stage() is None
    watchdog.suspend()
    now = 10_000
    assert watchdog._expired_stage() is None
    watchdog.arm("reading audio")
    assert watchdog._expired_stage() is None
    now += 91
    assert watchdog._expired_stage() == "reading audio"


def test_timeout_allows_multiple_normal_chunks() -> None:
    assert capture_timeout_seconds(30) == 90
    assert capture_timeout_seconds(120) == 360


@pytest.mark.parametrize("failure", ["open_hang", "read_hang", "missing_device"])
def test_listener_exits_for_service_restart_when_audio_never_progresses(
    tmp_path: Path, failure: str
) -> None:
    # Isolate os._exit from pytest and simulate a native call that never returns.
    script = """
import contextlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace
import family_recorder.listener as listener
from family_recorder.capture_watchdog import CaptureWatchdog
from family_recorder.config import AppConfig, AudioConfig, DirectionConfig, StorageConfig

failure = sys.argv[1]
class Recorder:
    def __init__(self, config):
        self.device = SimpleNamespace(index=0, name="test microphone")
        self.capture_sample_rate = 16000
    @contextlib.contextmanager
    def open_stream(self):
        if failure == "open_hang":
            time.sleep(60)
        if failure == "missing_device":
            raise RuntimeError("No input devices")
        yield object()
    def read_chunk(self, stream, **kwargs):
        time.sleep(60)

listener.AudioRecorder = Recorder
listener.WhisperCppTranscriber = lambda *args: SimpleNamespace(validate=lambda: None)
listener.CaptureWatchdog = lambda timeout: CaptureWatchdog(0.3)
listener.run_listener(AppConfig(
    audio=AudioConfig(retry_seconds=0.02),
    direction=DirectionConfig(enabled=False),
    storage=StorageConfig(data_dir=Path(sys.argv[2])),
))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", script, failure, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert result.returncode == 75, result.stderr
    assert "No completed audio capture" in result.stderr


def test_closed_watchdog_does_not_exit_process() -> None:
    with CaptureWatchdog(0.1) as watchdog:
        watchdog.arm("reading audio")
    assert not watchdog._thread.is_alive()
