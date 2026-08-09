#!/bin/bash
set -euo pipefail

for LABEL in com.familyrecorder.listener com.familyrecorder.summary; do
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  if [[ -f "$PLIST" ]]; then
    launchctl bootout "gui/$UID" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed $LABEL"
  fi
done
