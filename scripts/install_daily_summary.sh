#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_ROOT="${FAMILYRECORDER_RUNTIME_ROOT:-$HOME/Library/Application Support/FamilyRecorder}"
CONFIG_PATH="${FAMILYRECORDER_CONFIG:-$HOME/.config/familyrecorder/config.yaml}"
PROGRAM="$RUNTIME_ROOT/venv/bin/family-recorder"
APP_EXECUTABLE="$RUNTIME_ROOT/FamilyRecorder.app/Contents/MacOS/FamilyRecorder"
PLIST="$HOME/Library/LaunchAgents/com.familyrecorder.summary.plist"
TEMPLATE="$REPO_ROOT/launchd/com.familyrecorder.summary.plist.in"

if [[ ! -x "$PROGRAM" || ! -x "$APP_EXECUTABLE" || ! -f "$CONFIG_PATH" ]]; then
  echo "Run scripts/install_mac.sh and scripts/install_menubar.sh before installing launchd." >&2
  exit 1
fi

"$RUNTIME_ROOT/venv/bin/python" - "$CONFIG_PATH" <<'PY'
import sys
from family_recorder.config import load_config
from family_recorder.summary import check_codex_login, resolve_codex_binary

config = load_config(sys.argv[1])
binary = resolve_codex_binary(config.summary.codex_binary_path)
print(f"Using Codex: {binary}")
print(check_codex_login(config.summary, binary=binary))
PY

read -r HOUR MINUTE < <(
  "$RUNTIME_ROOT/venv/bin/python" - "$CONFIG_PATH" <<'PY'
import sys
from family_recorder.config import load_config

config = load_config(sys.argv[1])
print(config.summary.hour, config.summary.minute)
PY
)

LOG_DIR="$("$RUNTIME_ROOT/venv/bin/python" - "$CONFIG_PATH" <<'PY'
import sys
from family_recorder.config import load_config

print(load_config(sys.argv[1]).storage.data_dir / "logs")
PY
)"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
"$RUNTIME_ROOT/venv/bin/python" - \
  "$TEMPLATE" "$PLIST" "$APP_EXECUTABLE" "$PROGRAM" "$CONFIG_PATH" "$LOG_DIR" \
  "$HOUR" "$MINUTE" "$HOME" <<'PY'
import sys
from pathlib import Path
from xml.sax.saxutils import escape

template, target, app_executable, program, config, log_dir, hour, minute, home = sys.argv[1:]
text = Path(template).read_text(encoding="utf-8")
for marker, value in {
    "__APP_EXECUTABLE__": app_executable,
    "__PROGRAM__": program,
    "__CONFIG__": config,
    "__LOG_DIR__": log_dir,
    "__HOUR__": hour,
    "__MINUTE__": minute,
    "__HOME__": home,
}.items():
    text = text.replace(marker, escape(value))
Path(target).write_text(text, encoding="utf-8")
PY

plutil -lint "$PLIST"
launchctl bootout "gui/$UID" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
echo "Installed com.familyrecorder.summary for $(printf '%02d:%02d' "$HOUR" "$MINUTE")"
echo "Log: $LOG_DIR/summary.log"
