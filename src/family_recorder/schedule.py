"""Safely update and reload the user-level daily-summary LaunchAgent."""

from __future__ import annotations

import copy
import os
import plistlib
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from family_recorder.config_editor import update_yaml_values

SUMMARY_AGENT_LABEL = "com.familyrecorder.summary"
APP_BUNDLE_ID = "com.familyrecorder.app"
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class ScheduleUpdateError(RuntimeError):
    """The summary schedule could not be updated without risking a partial state."""


@dataclass(frozen=True)
class ScheduleUpdateResult:
    time_label: str
    launch_agent_reloaded: bool


def summary_agent_path() -> Path:
    """Return the standard user LaunchAgent path without creating it."""
    return Path.home() / "Library/LaunchAgents/com.familyrecorder.summary.plist"


def summary_agent_is_installed(path: Path | None = None) -> bool:
    """Report whether a regular, non-symlink schedule plist is installed."""
    target = path or summary_agent_path()
    return target.is_file() and not target.is_symlink()


def _atomic_bytes(path: Path, content: bytes, mode: int) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _run_launchctl(
    runner: CommandRunner,
    action: str,
    domain: str,
    plist_path: Path,
) -> subprocess.CompletedProcess[str]:
    return runner(
        ["/bin/launchctl", action, domain, str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def _validate_owned_plist(document: dict[str, object], config_path: Path) -> None:
    if document.get("Label") != SUMMARY_AGENT_LABEL:
        raise ScheduleUpdateError("拒絕修改識別碼不符的摘要排程")
    identifiers = document.get("AssociatedBundleIdentifiers")
    if identifiers != [APP_BUNDLE_ID]:
        raise ScheduleUpdateError("摘要排程沒有關聯至 FamilyRecorder App")
    arguments = document.get("ProgramArguments")
    if not isinstance(arguments, list) or "--config" not in arguments:
        raise ScheduleUpdateError("摘要排程缺少 FamilyRecorder 設定檔參數")
    config_index = arguments.index("--config") + 1
    if config_index >= len(arguments) or not isinstance(arguments[config_index], str):
        raise ScheduleUpdateError("摘要排程的設定檔參數無效")
    if Path(arguments[config_index]).expanduser().resolve() != config_path:
        raise ScheduleUpdateError("摘要排程使用不同的 FamilyRecorder 設定檔")


def update_summary_schedule(
    config_path: Path,
    hour: int,
    minute: int,
    *,
    plist_path: Path | None = None,
    command_runner: CommandRunner = subprocess.run,
    user_id: int | None = None,
) -> ScheduleUpdateResult:
    """Atomically save the time and reload an existing LaunchAgent.

    If the LaunchAgent has not been installed yet, the YAML value is still
    saved for the installer to use later. A reload failure restores both files
    and attempts to reactivate the original schedule.
    """
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("摘要時間必須介於 00:00 與 23:59")
    config_path = config_path.expanduser().resolve()
    target = plist_path or summary_agent_path()
    label = f"{hour:02d}:{minute:02d}"
    if target.is_symlink():
        raise ScheduleUpdateError("拒絕修改符號連結的摘要排程")

    original_config = config_path.read_bytes()
    config_mode = config_path.stat().st_mode & 0o777
    if not target.exists():
        update_yaml_values(config_path, "summary", {"hour": hour, "minute": minute})
        return ScheduleUpdateResult(label, False)
    if not target.is_file():
        raise ScheduleUpdateError("摘要排程不是一般檔案")

    original_plist = target.read_bytes()
    plist_mode = target.stat().st_mode & 0o777
    try:
        original_document = plistlib.loads(original_plist)
    except plistlib.InvalidFileException as exc:
        raise ScheduleUpdateError("摘要排程 plist 格式無效") from exc
    if not isinstance(original_document, dict):
        raise ScheduleUpdateError("摘要排程 plist 格式無效")
    _validate_owned_plist(original_document, config_path)
    updated_document = copy.deepcopy(original_document)
    updated_document["StartCalendarInterval"] = {"Hour": hour, "Minute": minute}
    updated_plist = plistlib.dumps(updated_document, fmt=plistlib.FMT_XML, sort_keys=False)

    domain = f"gui/{user_id if user_id is not None else os.getuid()}"
    try:
        update_yaml_values(config_path, "summary", {"hour": hour, "minute": minute})
        _atomic_bytes(target, updated_plist, plist_mode)
        _run_launchctl(command_runner, "bootout", domain, target)
        loaded = _run_launchctl(command_runner, "bootstrap", domain, target)
        if loaded.returncode != 0:
            detail = (loaded.stderr or loaded.stdout).strip()[:300]
            raise ScheduleUpdateError(f"無法重新載入每日摘要排程：{detail or 'launchctl 錯誤'}")
    except Exception as exc:
        _atomic_bytes(config_path, original_config, config_mode)
        _atomic_bytes(target, original_plist, plist_mode)
        _run_launchctl(command_runner, "bootout", domain, target)
        restored = _run_launchctl(command_runner, "bootstrap", domain, target)
        if restored.returncode != 0:
            detail = (restored.stderr or restored.stdout).strip()[:300]
            raise ScheduleUpdateError(
                f"{exc}；設定已還原，但原排程無法重新載入：{detail or 'launchctl 錯誤'}"
            ) from exc
        raise
    return ScheduleUpdateResult(label, True)
