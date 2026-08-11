#!/bin/bash
set -euo pipefail

RUNTIME_ROOT="${FAMILYRECORDER_RUNTIME_ROOT:-$HOME/Library/Application Support/FamilyRecorder}"
CONFIG_PATH="${FAMILYRECORDER_CONFIG:-$HOME/.config/familyrecorder/config.yaml}"
LAUNCH_AGENTS_ROOT="${FAMILYRECORDER_LAUNCH_AGENTS_ROOT:-$HOME/Library/LaunchAgents}"
TRASH_ROOT="${FAMILYRECORDER_TRASH_ROOT:-$HOME/.Trash}"
SKIP_LAUNCHCTL="${FAMILYRECORDER_SKIP_LAUNCHCTL:-0}"
DEFAULT_DATA_ROOT="$HOME/xvf3800-listener-data"
DATA_ROOT="${FAMILYRECORDER_DATA_ROOT:-}"

fail() {
  printf 'ERROR=%s\n' "$1" >&2
  exit 1
}

resolve_data_root() {
  if [[ -n "$DATA_ROOT" ]]; then
    printf '%s\n' "$DATA_ROOT"
    return
  fi
  if [[ -x "$RUNTIME_ROOT/venv/bin/python" && -f "$CONFIG_PATH" ]]; then
    "$RUNTIME_ROOT/venv/bin/python" - "$CONFIG_PATH" <<'PY' 2>/dev/null && return
import sys
from family_recorder.config import load_config

print(load_config(sys.argv[1]).storage.data_dir)
PY
  fi
  printf '%s\n' "$DEFAULT_DATA_ROOT"
}

size_bytes() {
  local target="$1"
  if [[ ! -e "$target" ]]; then
    printf '0\n'
    return
  fi
  local blocks
  blocks="$(du -sk "$target" 2>/dev/null | awk '{print $1}')"
  printf '%s\n' "$(( ${blocks:-0} * 1024 ))"
}

has_launch_agent() {
  local label
  for label in \
    com.familyrecorder.listener \
    com.familyrecorder.summary \
    com.familyrecorder.menubar; do
    [[ -f "$LAUNCH_AGENTS_ROOT/$label.plist" ]] && return 0
  done
  return 1
}

inspect_installation() {
  DATA_ROOT="$(resolve_data_root)"
  local runtime_bytes data_bytes config_bytes total installed
  runtime_bytes="$(size_bytes "$RUNTIME_ROOT")"
  data_bytes="$(size_bytes "$DATA_ROOT")"
  config_bytes="$(size_bytes "$(dirname "$CONFIG_PATH")")"
  total="$((runtime_bytes + data_bytes + config_bytes))"
  installed=0
  if [[ -e "$RUNTIME_ROOT" || -e "$CONFIG_PATH" || -e "$DATA_ROOT" ]] || has_launch_agent; then
    installed=1
  fi
  printf 'INSTALLED=%s\n' "$installed"
  printf 'RUNTIME_PATH=%s\n' "$RUNTIME_ROOT"
  printf 'DATA_PATH=%s\n' "$DATA_ROOT"
  printf 'CONFIG_PATH=%s\n' "$CONFIG_PATH"
  printf 'RUNTIME_BYTES=%s\n' "$runtime_bytes"
  printf 'DATA_BYTES=%s\n' "$data_bytes"
  printf 'CONFIG_BYTES=%s\n' "$config_bytes"
  printf 'TOTAL_BYTES=%s\n' "$total"
}

validate_removal_target() {
  local target="$1" label="$2"
  [[ -n "$target" ]] || fail "$label 路徑為空，已停止解除安裝。"
  [[ "$target" == /* ]] || fail "$label 不是絕對路徑，已停止解除安裝：$target"
  case "$target" in
    /|"$HOME"|"$TRASH_ROOT"|"$LAUNCH_AGENTS_ROOT")
      fail "$label 指向受保護的位置，已停止解除安裝：$target"
      ;;
  esac
}

unique_trash_session() {
  local base="$TRASH_ROOT/FamilyRecorder-$(date +%Y%m%d-%H%M%S)"
  if [[ -e "$base" ]]; then
    base="$base-$$"
  fi
  printf '%s\n' "$base"
}

move_into() {
  local source="$1" destination="$2"
  [[ -e "$source" ]] || return 0
  mkdir -p "$destination"
  mv "$source" "$destination/"
}

stop_and_move_agents() {
  local trash_session="$1" label plist
  for label in \
    com.familyrecorder.listener \
    com.familyrecorder.summary \
    com.familyrecorder.menubar; do
    plist="$LAUNCH_AGENTS_ROOT/$label.plist"
    if [[ "$SKIP_LAUNCHCTL" != "1" ]] && command -v launchctl >/dev/null 2>&1; then
      if [[ -f "$plist" ]]; then
        launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
      else
        launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
      fi
    fi
    move_into "$plist" "$trash_session/背景服務"
  done
}

move_config() {
  local trash_session="$1" config_parent
  config_parent="$(dirname "$CONFIG_PATH")"
  validate_removal_target "$config_parent" "設定"
  if [[ "$(basename "$config_parent")" == "familyrecorder" ]]; then
    move_into "$config_parent" "$trash_session/設定"
    return
  fi
  move_into "$CONFIG_PATH" "$trash_session/設定"
  local backup
  for backup in "$CONFIG_PATH".backup-*; do
    [[ -e "$backup" ]] && move_into "$backup" "$trash_session/設定"
  done
}

data_root_is_dedicated() {
  [[ "$DATA_ROOT" == "$DEFAULT_DATA_ROOT" ]] && return 0
  [[ -f "$DATA_ROOT/.familyrecorder-data" ]] || return 1
  local child name
  while IFS= read -r child; do
    name="$(basename "$child")"
    case "$name" in
      audio|transcripts|summaries|logs|speaker-profiles|placement-tests|\
        listener.sqlite3|listener.sqlite3-shm|listener.sqlite3-wal|control.json|\
        .familyrecorder-data)
        ;;
      *)
        return 1
        ;;
    esac
  done < <(find "$DATA_ROOT" -mindepth 1 -maxdepth 1 -print 2>/dev/null)
  return 0
}

move_data() {
  local trash_session="$1"
  validate_removal_target "$DATA_ROOT" "家庭資料"
  if data_root_is_dedicated; then
    move_into "$DATA_ROOT" "$trash_session/家庭資料"
    return
  fi

  # Older or custom installations may not have a marker. Move only known
  # FamilyRecorder-owned entries so a broad custom data_dir cannot remove
  # unrelated files.
  local entry
  for entry in \
    audio transcripts summaries logs speaker-profiles placement-tests \
    listener.sqlite3 listener.sqlite3-shm listener.sqlite3-wal control.json \
    .familyrecorder-data; do
    move_into "$DATA_ROOT/$entry" "$trash_session/家庭資料/FamilyRecorder-files"
  done
  rmdir "$DATA_ROOT" 2>/dev/null || true
}

uninstall() {
  local mode="$1"
  case "$mode" in
    keep-data|all) ;;
    *) fail "未知的解除安裝模式：$mode" ;;
  esac

  DATA_ROOT="$(resolve_data_root)"
  validate_removal_target "$RUNTIME_ROOT" "程式與模型"
  validate_removal_target "$DATA_ROOT" "家庭資料"
  validate_removal_target "$(dirname "$CONFIG_PATH")" "設定"
  mkdir -p "$TRASH_ROOT"
  local trash_session
  trash_session="$(unique_trash_session)"
  mkdir -p "$trash_session"

  stop_and_move_agents "$trash_session"
  if [[ "$mode" == "all" ]]; then
    move_data "$trash_session"
    move_config "$trash_session"
  fi

  if command -v tccutil >/dev/null 2>&1; then
    tccutil reset Microphone com.familyrecorder.app >/dev/null 2>&1 || true
    tccutil reset Microphone com.familyrecorder.menubar >/dev/null 2>&1 || true
    for service in Calendar CalendarFullAccess CalendarWriteOnly; do
      tccutil reset "$service" com.familyrecorder.app >/dev/null 2>&1 || true
      tccutil reset "$service" com.familyrecorder.menubar >/dev/null 2>&1 || true
    done
  fi
  move_into "$RUNTIME_ROOT" "$trash_session/程式與模型"

  printf 'UNINSTALL_OK=1\n'
  printf 'MODE=%s\n' "$mode"
  printf 'TRASH_PATH=%s\n' "$trash_session"
  if [[ "$mode" == "keep-data" ]]; then
    printf 'PRESERVED_DATA_PATH=%s\n' "$DATA_ROOT"
    printf 'PRESERVED_CONFIG_PATH=%s\n' "$CONFIG_PATH"
  fi
}

command="${1:-inspect}"
case "$command" in
  inspect)
    inspect_installation
    ;;
  uninstall)
    uninstall "${2:-}"
    ;;
  *)
    fail "未知操作：$command"
    ;;
esac
