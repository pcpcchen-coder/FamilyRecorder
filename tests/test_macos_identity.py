from __future__ import annotations

import plistlib
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP_BUNDLE_ID = "com.familyrecorder.app"
APP_EXECUTABLE = "/Library/Application Support/FamilyRecorder.app/Contents/MacOS/FamilyRecorder"
PROGRAM = "/Library/Application Support/FamilyRecorder/venv/bin/family-recorder"


def _load_template(name: str) -> dict[str, object]:
    text = (ROOT / "launchd" / name).read_text(encoding="utf-8")
    replacements = {
        "__APP_EXECUTABLE__": APP_EXECUTABLE,
        "__PROGRAM__": PROGRAM,
        "__CONFIG__": "/tmp/config.yaml",
        "__LOG_DIR__": "/tmp/logs",
        "__HOME__": "/tmp/home",
        "__HOUR__": "0",
        "__MINUTE__": "10",
        "__UNINSTALLER__": "/tmp/解除安裝 FamilyRecorder.app",
    }
    for marker, value in replacements.items():
        text = text.replace(marker, value)
    return plistlib.loads(text.encode())


def test_app_bundle_uses_the_familyrecorder_identity() -> None:
    info = plistlib.loads((ROOT / "menubar" / "Info.plist").read_bytes())

    assert info["CFBundleDisplayName"] == "FamilyRecorder"
    assert info["CFBundleName"] == "FamilyRecorder"
    assert info["CFBundleExecutable"] == "FamilyRecorder"
    assert info["CFBundleIdentifier"] == APP_BUNDLE_ID
    assert "FamilyRecorder" in info["NSMicrophoneUsageDescription"]


def test_every_launch_agent_is_associated_with_the_same_app() -> None:
    services = {
        "com.familyrecorder.listener.plist.in": "listener",
        "com.familyrecorder.summary.plist.in": "summary",
    }
    for template_name, service in services.items():
        plist = _load_template(template_name)
        arguments = plist["ProgramArguments"]
        assert plist["AssociatedBundleIdentifiers"] == [APP_BUNDLE_ID]
        assert arguments[:5] == [
            APP_EXECUTABLE,
            "--service",
            service,
            "--program",
            PROGRAM,
        ]

    menubar = _load_template("com.familyrecorder.menubar.plist.in")
    assert menubar["AssociatedBundleIdentifiers"] == [APP_BUNDLE_ID]
    assert menubar["ProgramArguments"][0] == APP_EXECUTABLE


def test_installer_builds_the_app_before_starting_the_listener() -> None:
    payload = (ROOT / "packaging" / "install_payload.sh").read_text(encoding="utf-8")

    assert payload.index('"$PAYLOAD_ROOT/scripts/install_menubar.sh"') < payload.index(
        '"$PAYLOAD_ROOT/scripts/install_launchd.sh"'
    )


def test_service_installers_launch_the_native_app_wrapper() -> None:
    for script_name in ("install_launchd.sh", "install_daily_summary.sh"):
        script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert 'FamilyRecorder.app/Contents/MacOS/FamilyRecorder"' in script
        assert '"__APP_EXECUTABLE__": app_executable' in script


def test_menu_installer_authorizes_through_launch_services() -> None:
    script = (ROOT / "scripts" / "install_menubar.sh").read_text(encoding="utf-8")

    assert '/usr/bin/open -n -W "$APP_ROOT" --args --authorize-microphone' in script
