#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The FamilyRecorder menu bar app supports macOS only." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_ROOT="${FAMILYRECORDER_RUNTIME_ROOT:-$HOME/Library/Application Support/FamilyRecorder}"
CONFIG_PATH="${FAMILYRECORDER_CONFIG:-$HOME/.config/familyrecorder/config.yaml}"
PROGRAM="$RUNTIME_ROOT/venv/bin/family-recorder"
APP_ROOT="$RUNTIME_ROOT/FamilyRecorder.app"
APP_EXECUTABLE="$APP_ROOT/Contents/MacOS/FamilyRecorder"
UNINSTALLER_ROOT="$RUNTIME_ROOT/解除安裝 FamilyRecorder.app"
UNINSTALLER_EXECUTABLE="$UNINSTALLER_ROOT/Contents/MacOS/FamilyRecorderUninstaller"
UNINSTALLER_RESOURCES="$UNINSTALLER_ROOT/Contents/Resources"
PLIST="$HOME/Library/LaunchAgents/com.familyrecorder.menubar.plist"
LISTENER_PLIST="$HOME/Library/LaunchAgents/com.familyrecorder.listener.plist"
SUMMARY_PLIST="$HOME/Library/LaunchAgents/com.familyrecorder.summary.plist"
TEMPLATE="$REPO_ROOT/launchd/com.familyrecorder.menubar.plist.in"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

if [[ ! -x "$PROGRAM" || ! -f "$CONFIG_PATH" ]]; then
  echo "Run scripts/install_mac.sh before installing the menu bar app." >&2
  exit 1
fi
if ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "Xcode Command Line Tools with Swift are required." >&2
  exit 1
fi

LOG_DIR="$("$RUNTIME_ROOT/venv/bin/python" - "$CONFIG_PATH" <<'PY'
import sys
from family_recorder.config import load_config

print(load_config(sys.argv[1]).storage.data_dir / "logs")
PY
)"

# Stop every process hosted by this bundle before replacing its executable.
# Remember existing services so running this helper by itself is also safe.
LISTENER_WAS_LOADED=false
SUMMARY_WAS_LOADED=false
launchctl print "gui/$UID/com.familyrecorder.listener" >/dev/null 2>&1 && \
  LISTENER_WAS_LOADED=true
launchctl print "gui/$UID/com.familyrecorder.summary" >/dev/null 2>&1 && \
  SUMMARY_WAS_LOADED=true
launchctl bootout "gui/$UID" "$PLIST" 2>/dev/null || true
launchctl bootout "gui/$UID" "$LISTENER_PLIST" 2>/dev/null || true
launchctl bootout "gui/$UID" "$SUMMARY_PLIST" 2>/dev/null || true
mkdir -p \
  "$APP_ROOT/Contents/MacOS" \
  "$UNINSTALLER_ROOT/Contents/MacOS" \
  "$UNINSTALLER_RESOURCES" \
  "$HOME/Library/LaunchAgents" \
  "$LOG_DIR"
if [[ -x "$LSREGISTER" && -d "$APP_ROOT" ]]; then
  "$LSREGISTER" -u "$APP_ROOT" >/dev/null 2>&1 || true
fi
rm -f "$APP_ROOT/Contents/MacOS/FamilyRecorderMenuBar"
xcrun swiftc -O -swift-version 5 -framework AppKit -framework AVFoundation \
  "$REPO_ROOT/menubar/FamilyRecorderMenuBar.swift" \
  -o "$APP_EXECUTABLE"
install -m 644 "$REPO_ROOT/menubar/Info.plist" "$APP_ROOT/Contents/Info.plist"
codesign --force --deep --sign - "$APP_ROOT"
plutil -lint "$APP_ROOT/Contents/Info.plist"

# Register the bundle before loading the associated LaunchAgents so macOS can
# attribute every background item and protected-resource request to the
# user-facing FamilyRecorder app instead of its Python worker executable.
if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$APP_ROOT"
fi

xcrun swiftc -O -parse-as-library -swift-version 5 -framework AppKit \
  "$REPO_ROOT/packaging/FamilyRecorderUninstaller.swift" \
  -o "$UNINSTALLER_EXECUTABLE"
install -m 644 \
  "$REPO_ROOT/packaging/UninstallerInfo.plist" \
  "$UNINSTALLER_ROOT/Contents/Info.plist"
install -m 755 \
  "$REPO_ROOT/scripts/uninstall_family_recorder.sh" \
  "$UNINSTALLER_RESOURCES/uninstall_family_recorder.sh"
codesign --force --deep --sign - "$UNINSTALLER_ROOT"
plutil -lint "$UNINSTALLER_ROOT/Contents/Info.plist"

"$RUNTIME_ROOT/venv/bin/python" - \
  "$TEMPLATE" "$PLIST" "$APP_EXECUTABLE" "$PROGRAM" "$CONFIG_PATH" "$LOG_DIR" \
  "$UNINSTALLER_ROOT" <<'PY'
import sys
from pathlib import Path
from xml.sax.saxutils import escape

template, target, executable, program, config, log_dir, uninstaller = sys.argv[1:]
text = Path(template).read_text(encoding="utf-8")
for marker, value in {
    "__APP_EXECUTABLE__": executable,
    "__PROGRAM__": program,
    "__CONFIG__": config,
    "__LOG_DIR__": log_dir,
    "__UNINSTALLER__": uninstaller,
}.items():
    text = text.replace(marker, escape(value))
Path(target).write_text(text, encoding="utf-8")
PY

plutil -lint "$PLIST"
launchctl bootstrap "gui/$UID" "$PLIST"
if [[ "$LISTENER_WAS_LOADED" == true && -f "$LISTENER_PLIST" ]]; then
  launchctl bootstrap "gui/$UID" "$LISTENER_PLIST"
fi
if [[ "$SUMMARY_WAS_LOADED" == true && -f "$SUMMARY_PLIST" ]]; then
  launchctl bootstrap "gui/$UID" "$SUMMARY_PLIST"
fi
echo "Installed and started the FamilyRecorder menu bar app"
echo "The menu app will request microphone access without blocking the installer."
