from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "uninstall_family_recorder.sh"


def _environment(tmp_path: Path, *, data_root: Path | None = None) -> dict[str, str]:
    home = tmp_path / "home"
    runtime = home / "Library" / "Application Support" / "FamilyRecorder"
    config = home / ".config" / "familyrecorder" / "config.yaml"
    data = data_root or home / "xvf3800-listener-data"
    agents = home / "Library" / "LaunchAgents"
    trash = home / ".Trash"
    for directory in (runtime, config.parent, data, agents, trash):
        directory.mkdir(parents=True, exist_ok=True)
    (runtime / "model.bin").write_bytes(b"model")
    config.write_text("storage:\n  data_dir: ignored-in-test\n", encoding="utf-8")
    (data / ".familyrecorder-data").write_text("", encoding="utf-8")
    (data / "transcripts").mkdir(exist_ok=True)
    (data / "transcripts" / "today.md").write_text("private", encoding="utf-8")
    for label in (
        "com.familyrecorder.listener",
        "com.familyrecorder.summary",
        "com.familyrecorder.menubar",
    ):
        (agents / f"{label}.plist").write_text(label, encoding="utf-8")
    return {
        **os.environ,
        "HOME": str(home),
        "FAMILYRECORDER_RUNTIME_ROOT": str(runtime),
        "FAMILYRECORDER_CONFIG": str(config),
        "FAMILYRECORDER_DATA_ROOT": str(data),
        "FAMILYRECORDER_LAUNCH_AGENTS_ROOT": str(agents),
        "FAMILYRECORDER_TRASH_ROOT": str(trash),
        "FAMILYRECORDER_SKIP_LAUNCHCTL": "1",
    }


def _run(
    tmp_path: Path, *arguments: str, data_root: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), *arguments],
        env=_environment(tmp_path, data_root=data_root),
        check=False,
        capture_output=True,
        text=True,
    )


def _value(output: str, key: str) -> str:
    return next(line.split("=", 1)[1] for line in output.splitlines() if line.startswith(f"{key}="))


def test_inspect_reports_installed_paths_and_sizes(tmp_path: Path) -> None:
    result = _run(tmp_path, "inspect")

    assert result.returncode == 0, result.stderr
    assert "INSTALLED=1" in result.stdout
    assert int(_value(result.stdout, "RUNTIME_BYTES")) > 0
    assert int(_value(result.stdout, "DATA_BYTES")) > 0
    assert int(_value(result.stdout, "TOTAL_BYTES")) > 0


def test_keep_data_removes_runtime_and_agents_but_preserves_private_data(tmp_path: Path) -> None:
    result = _run(tmp_path, "uninstall", "keep-data")

    assert result.returncode == 0, result.stderr
    assert "UNINSTALL_OK=1" in result.stdout
    home = tmp_path / "home"
    assert not (home / "Library" / "Application Support" / "FamilyRecorder").exists()
    assert not any((home / "Library" / "LaunchAgents").glob("com.familyrecorder.*.plist"))
    assert (home / "xvf3800-listener-data" / "transcripts" / "today.md").is_file()
    assert (home / ".config" / "familyrecorder" / "config.yaml").is_file()
    assert Path(_value(result.stdout, "TRASH_PATH")).is_dir()


def test_full_uninstall_moves_runtime_config_and_marked_data_to_trash(tmp_path: Path) -> None:
    result = _run(tmp_path, "uninstall", "all")

    assert result.returncode == 0, result.stderr
    home = tmp_path / "home"
    assert not (home / "Library" / "Application Support" / "FamilyRecorder").exists()
    assert not (home / "xvf3800-listener-data").exists()
    assert not (home / ".config" / "familyrecorder").exists()
    trash_session = Path(_value(result.stdout, "TRASH_PATH"))
    assert (trash_session / "程式與模型" / "FamilyRecorder" / "model.bin").is_file()
    assert (
        trash_session / "家庭資料" / "xvf3800-listener-data" / "transcripts" / "today.md"
    ).is_file()
    assert (trash_session / "設定" / "familyrecorder" / "config.yaml").is_file()


def test_marked_custom_data_directory_keeps_unrelated_files(tmp_path: Path) -> None:
    shared = tmp_path / "home" / "Documents"
    result_environment = _environment(tmp_path, data_root=shared)
    (shared / "unrelated.txt").write_text("keep me", encoding="utf-8")

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "uninstall", "all"],
        env=result_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (shared / "unrelated.txt").read_text(encoding="utf-8") == "keep me"
    assert not (shared / "transcripts").exists()


def test_marked_dedicated_custom_data_directory_moves_as_one_unit(tmp_path: Path) -> None:
    dedicated = tmp_path / "home" / "Family Journal"

    result = _run(tmp_path, "uninstall", "all", data_root=dedicated)

    assert result.returncode == 0, result.stderr
    assert not dedicated.exists()
    trash_session = Path(_value(result.stdout, "TRASH_PATH"))
    assert (trash_session / "家庭資料" / "Family Journal" / "transcripts" / "today.md").is_file()
