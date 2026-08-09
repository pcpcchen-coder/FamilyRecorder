from datetime import UTC, datetime, timedelta
from pathlib import Path

from family_recorder.control import pause_recording, read_pause_state, resume_recording


def test_timed_pause_expires_automatically(tmp_path: Path) -> None:
    now = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    state = pause_recording(tmp_path, minutes=15, now=now)
    assert state.paused is True
    assert state.until == now + timedelta(minutes=15)
    assert read_pause_state(tmp_path, now + timedelta(minutes=14)).paused is True

    expired = read_pause_state(tmp_path, now + timedelta(minutes=16))
    assert expired.paused is False
    assert not (tmp_path / "control.json").exists()


def test_indefinite_pause_requires_resume(tmp_path: Path) -> None:
    state = pause_recording(tmp_path)
    assert state.paused is True
    assert state.until is None
    assert "手動恢復" in state.label

    resumed = resume_recording(tmp_path)
    assert resumed.paused is False
    assert read_pause_state(tmp_path).paused is False
