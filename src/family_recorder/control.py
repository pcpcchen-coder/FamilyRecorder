from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


class ControlStateError(RuntimeError):
    """Raised when the listener control state cannot be read or written."""


@dataclass(frozen=True)
class PauseState:
    paused: bool
    until: datetime | None = None

    @property
    def label(self) -> str:
        if not self.paused:
            return "錄音中"
        if self.until is None:
            return "已暫停，直到手動恢復"
        return f"已暫停，預計 {self.until.astimezone():%H:%M} 自動恢復"


def control_path(data_dir: Path) -> Path:
    return data_dir / "control.json"


def read_pause_state(data_dir: Path, now: datetime | None = None) -> PauseState:
    now = now or datetime.now().astimezone()
    path = control_path(data_dir)
    if not path.is_file():
        return PauseState(False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("paused") is not True:
            return PauseState(False)
        raw_until = raw.get("until")
        until = datetime.fromisoformat(raw_until) if raw_until else None
        if until is not None and until.tzinfo is None:
            raise ValueError("pause deadline must include a timezone")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ControlStateError(f"Invalid listener control state at {path}: {exc}") from exc
    if until is not None and until <= now:
        path.unlink(missing_ok=True)
        return PauseState(False)
    return PauseState(True, until)


def pause_recording(
    data_dir: Path,
    *,
    minutes: int | None = None,
    now: datetime | None = None,
) -> PauseState:
    if minutes is not None and minutes < 1:
        raise ValueError("Pause duration must be at least one minute")
    now = now or datetime.now().astimezone()
    until = now + timedelta(minutes=minutes) if minutes is not None else None
    state = PauseState(True, until)
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "paused": True,
        "until": until.isoformat() if until is not None else None,
        "updated_at": now.isoformat(),
    }
    handle, temporary = tempfile.mkstemp(prefix=".control-", suffix=".json", dir=data_dir)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, control_path(data_dir))
    finally:
        Path(temporary).unlink(missing_ok=True)
    return state


def resume_recording(data_dir: Path) -> PauseState:
    control_path(data_dir).unlink(missing_ok=True)
    return PauseState(False)
