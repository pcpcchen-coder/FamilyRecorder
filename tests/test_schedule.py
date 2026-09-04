from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

import pytest

from family_recorder.config import load_config
from family_recorder.schedule import (
    APP_BUNDLE_ID,
    SUMMARY_AGENT_LABEL,
    ScheduleUpdateError,
    summary_agent_is_installed,
    update_summary_schedule,
)


def schedule_plist(config_path: Path, hour: int = 0, minute: int = 10) -> bytes:
    return plistlib.dumps(
        {
            "Label": SUMMARY_AGENT_LABEL,
            "AssociatedBundleIdentifiers": [APP_BUNDLE_ID],
            "ProgramArguments": [
                "/Applications/FamilyRecorder.app/Contents/MacOS/FamilyRecorder",
                "--service",
                "summary",
                "--program",
                "/tmp/family-recorder",
                "--config",
                str(config_path),
            ],
            "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        },
        sort_keys=False,
    )


class Launchctl:
    def __init__(self, bootstrap_results: list[int] | None = None):
        self.calls: list[list[str]] = []
        self.bootstrap_results = iter(bootstrap_results or [0])

    def __call__(self, arguments, **kwargs):
        self.calls.append(arguments)
        assert kwargs == {
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 15,
        }
        result = next(self.bootstrap_results) if arguments[1] == "bootstrap" else 0
        return subprocess.CompletedProcess(
            arguments,
            result,
            stdout="",
            stderr="simulated launchctl failure" if result else "",
        )


def test_schedule_update_saves_both_values_and_reloads_launch_agent(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("# preserve\nsummary:\n  hour: 0\n  minute: 10\n")
    config.chmod(0o600)
    plist = tmp_path / "com.familyrecorder.summary.plist"
    plist.write_bytes(schedule_plist(config))
    plist.chmod(0o644)
    calls = Launchctl()

    result = update_summary_schedule(
        config, 8, 35, plist_path=plist, command_runner=calls, user_id=501
    )

    loaded = load_config(config)
    document = plistlib.loads(plist.read_bytes())
    assert result.time_label == "08:35"
    assert result.launch_agent_reloaded
    assert loaded.summary.hour == 8 and loaded.summary.minute == 35
    assert "# preserve" in config.read_text()
    assert config.stat().st_mode & 0o777 == 0o600
    assert plist.stat().st_mode & 0o777 == 0o644
    assert document["StartCalendarInterval"] == {"Hour": 8, "Minute": 35}
    assert [call[1:3] for call in calls.calls] == [
        ["bootout", "gui/501"],
        ["bootstrap", "gui/501"],
    ]


def test_missing_launch_agent_saves_time_without_running_launchctl(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("{}\n")
    plist = tmp_path / "missing.plist"

    def forbidden(*_args, **_kwargs):
        pytest.fail("launchctl must not run when the schedule is not installed")

    result = update_summary_schedule(config, 23, 59, plist_path=plist, command_runner=forbidden)

    assert not result.launch_agent_reloaded
    assert load_config(config).summary.hour == 23
    assert load_config(config).summary.minute == 59
    assert not plist.exists()


def test_bootstrap_failure_restores_exact_config_and_original_schedule(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    original_config = b"# exact\nsummary:\n  hour: 0\n  minute: 10\n"
    config.write_bytes(original_config)
    plist = tmp_path / "com.familyrecorder.summary.plist"
    original_plist = schedule_plist(config)
    plist.write_bytes(original_plist)
    calls = Launchctl([5, 0])

    with pytest.raises(ScheduleUpdateError, match="simulated launchctl failure"):
        update_summary_schedule(config, 12, 34, plist_path=plist, command_runner=calls, user_id=501)

    assert config.read_bytes() == original_config
    assert plist.read_bytes() == original_plist
    assert [call[1] for call in calls.calls] == [
        "bootout",
        "bootstrap",
        "bootout",
        "bootstrap",
    ]


@pytest.mark.parametrize("hour,minute", [(-1, 0), (24, 0), (0, -1), (0, 60)])
def test_invalid_time_changes_nothing(tmp_path: Path, hour: int, minute: int) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("summary:\n  hour: 0\n  minute: 10\n")
    before = config.read_bytes()
    with pytest.raises(ValueError, match="00:00"):
        update_summary_schedule(config, hour, minute, plist_path=tmp_path / "missing")
    assert config.read_bytes() == before


def test_unrecognized_or_symlinked_plist_is_never_modified(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("summary:\n  hour: 0\n  minute: 10\n")
    wrong = tmp_path / "wrong.plist"
    wrong.write_bytes(schedule_plist(config).replace(SUMMARY_AGENT_LABEL.encode(), b"other.job"))
    before = (config.read_bytes(), wrong.read_bytes())
    with pytest.raises(ScheduleUpdateError, match="識別碼"):
        update_summary_schedule(config, 7, 20, plist_path=wrong)
    assert (config.read_bytes(), wrong.read_bytes()) == before

    link = tmp_path / "link.plist"
    link.symlink_to(wrong)
    assert not summary_agent_is_installed(link)
    with pytest.raises(ScheduleUpdateError, match="符號連結"):
        update_summary_schedule(config, 7, 20, plist_path=link)
