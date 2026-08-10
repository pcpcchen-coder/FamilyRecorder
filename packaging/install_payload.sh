#!/bin/bash
set -euo pipefail

RESOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_ROOT="$RESOURCE_ROOT/FamilyRecorderPayload"
RUNTIME_ROOT="${FAMILYRECORDER_RUNTIME_ROOT:-$HOME/Library/Application Support/FamilyRecorder}"
CONFIG_PATH="${FAMILYRECORDER_CONFIG:-$HOME/.config/familyrecorder/config.yaml}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.codex/bin:/usr/bin:/bin:/usr/sbin:/sbin"

log() {
  printf '%s\n' "$1"
}

fail() {
  printf '錯誤：%s\n' "$1" >&2
  exit 1
}

find_brew() {
  if [[ -x /opt/homebrew/bin/brew ]]; then
    printf '%s\n' /opt/homebrew/bin/brew
  elif command -v brew >/dev/null 2>&1; then
    command -v brew
  fi
}

find_codex() {
  local candidate
  for candidate in \
    "$(command -v codex 2>/dev/null || true)" \
    "$HOME/.local/bin/codex" \
    "$HOME/.codex/bin/codex" \
    "/Applications/ChatGPT.app/Contents/Resources/codex" \
    "/opt/homebrew/bin/codex" \
    "/usr/local/bin/codex"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

codex_is_logged_in() {
  local codex_bin
  codex_bin="$(find_codex)" || return 1
  "$codex_bin" login status >/dev/null 2>&1
}

preflight() {
  local brew_bin codex_bin auth_detail
  brew_bin="$(find_brew || true)"
  codex_bin="$(find_codex || true)"
  printf 'ARCH=%s\n' "$(uname -m)"
  printf 'MACOS=%s\n' "$(sw_vers -productVersion)"
  printf 'HOMEBREW=%s\n' "$brew_bin"
  printf 'SWIFTC=%s\n' "$(xcrun --find swiftc 2>/dev/null || true)"
  printf 'CODEX=%s\n' "$codex_bin"
  if [[ -n "$codex_bin" ]] && auth_detail="$($codex_bin login status 2>&1)"; then
    printf 'CODEX_AUTH=1\n'
    printf 'CODEX_AUTH_DETAIL=%s\n' "${auth_detail//$'\n'/ }"
  else
    printf 'CODEX_AUTH=0\n'
    printf 'CODEX_AUTH_DETAIL=%s\n' "${auth_detail:-尚未登入 ChatGPT}"
  fi
}

install_codex() (
  local temporary installer codex_bin
  temporary="$(mktemp -d -t familyrecorder-codex)"
  installer="$temporary/install-codex.sh"
  trap 'rm -rf "$temporary"' EXIT
  log "正在從 OpenAI 官方網址下載 Codex CLI 安裝器…"
  /usr/bin/curl --fail --silent --show-error --location \
    https://chatgpt.com/codex/install.sh -o "$installer"
  chmod 700 "$installer"
  log "正在安裝官方 Codex CLI 到使用者目錄…"
  CODEX_NON_INTERACTIVE=true /bin/sh "$installer"
  codex_bin="$(find_codex || true)"
  [[ -n "$codex_bin" ]] || fail "Codex CLI 安裝完成後仍找不到執行檔。"
  log "Codex CLI 已就緒：$codex_bin"
)

login_codex() {
  local codex_bin
  codex_bin="$(find_codex || true)"
  [[ -n "$codex_bin" ]] || fail "尚未安裝 Codex CLI，請先按「安裝官方 Codex CLI」。"
  log "瀏覽器即將開啟。請選擇「Sign in with ChatGPT」並完成登入…"
  "$codex_bin" login
  "$codex_bin" login status
}

login_codex_with_device_code() {
  local codex_bin
  codex_bin="$(find_codex || true)"
  [[ -n "$codex_bin" ]] || fail "尚未安裝 Codex CLI，請先按「安裝官方 Codex CLI」。"
  log "正在啟動裝置碼登入；請依畫面指示在瀏覽器輸入代碼…"
  "$codex_bin" login --device-auth
  "$codex_bin" login status
}

validate_payload() {
  [[ -x "$PAYLOAD_ROOT/scripts/install_mac.sh" ]] || fail "DMG 安裝資源不完整。"
  [[ -x "$PAYLOAD_ROOT/scripts/uninstall_family_recorder.sh" ]] || \
    fail "DMG 缺少解除安裝程式。"
  [[ -f "$PAYLOAD_ROOT/config.example.yaml" ]] || fail "DMG 缺少設定範例。"
  [[ -f "$PAYLOAD_ROOT/packaging/FamilyRecorderUninstaller.swift" ]] || \
    fail "DMG 缺少原生解除安裝介面。"
  [[ -f "$PAYLOAD_ROOT/packaging/UninstallerInfo.plist" ]] || \
    fail "DMG 缺少解除安裝器資訊。"
  compgen -G "$PAYLOAD_ROOT/wheel/family_recorder-*.whl" >/dev/null || \
    fail "DMG 缺少 FamilyRecorder wheel。"
}

install_family_recorder() {
  local model="$1" wheel backup codex_bin
  case "$model" in
    small|medium|large-v3-turbo) ;;
    *) fail "不支援的 Whisper 模型：$model" ;;
  esac
  [[ "$(uname -m)" == "arm64" ]] || fail "此安裝包只支援 Apple Silicon Mac。"
  [[ -n "$(find_brew || true)" ]] || fail "請先安裝 Homebrew，再重新執行。"
  xcrun --find swiftc >/dev/null 2>&1 || \
    fail "找不到 Apple Command Line Tools；請先完成 Homebrew 的安裝需求。"
  validate_payload
  wheel="$(find "$PAYLOAD_ROOT/wheel" -maxdepth 1 -name 'family_recorder-*.whl' -print -quit)"

  log "準備安裝 FamilyRecorder，Whisper 模型：$model"
  if [[ -f "$CONFIG_PATH" ]]; then
    backup="$CONFIG_PATH.backup-$(date +%Y%m%d-%H%M%S)"
    cp -p "$CONFIG_PATH" "$backup"
    log "已備份原有設定：$backup"
  fi

  FAMILYRECORDER_PACKAGE="$wheel" \
  FAMILYRECORDER_RUNTIME_ROOT="$RUNTIME_ROOT" \
  FAMILYRECORDER_CONFIG="$CONFIG_PATH" \
  WHISPER_MODEL="$model" \
    "$PAYLOAD_ROOT/scripts/install_mac.sh"

  log "正在安裝選單列控制程式…"
  FAMILYRECORDER_RUNTIME_ROOT="$RUNTIME_ROOT" \
  FAMILYRECORDER_CONFIG="$CONFIG_PATH" \
    "$PAYLOAD_ROOT/scripts/install_menubar.sh"

  log "正在啟用錄音常駐服務…"
  FAMILYRECORDER_RUNTIME_ROOT="$RUNTIME_ROOT" \
  FAMILYRECORDER_CONFIG="$CONFIG_PATH" \
    "$PAYLOAD_ROOT/scripts/install_launchd.sh"

  codex_bin="$(find_codex || true)"
  if [[ -n "$codex_bin" ]] && codex_is_logged_in; then
    log "正在安裝每日純文字摘要排程…"
    FAMILYRECORDER_RUNTIME_ROOT="$RUNTIME_ROOT" \
    FAMILYRECORDER_CONFIG="$CONFIG_PATH" \
      "$PAYLOAD_ROOT/scripts/install_daily_summary.sh"
  else
    log "提醒：尚未完成 ChatGPT 登入，因此暫不安裝每日摘要排程。"
    log "登入後可重新開啟本安裝器，再按一次「安裝 FamilyRecorder」。"
  fi

  log ""
  log "安裝完成。請接上 XVF3800，並在 macOS 系統設定允許麥克風權限。"
  log "選單列出現波形圖示後，即可暫停錄音、開啟逐字稿與切換已下載模型。"
}

dry_run() {
  local model="$1"
  validate_payload
  case "$model" in
    small|medium|large-v3-turbo) ;;
    *) fail "不支援的 Whisper 模型：$model" ;;
  esac
  log "DRY_RUN_OK=1"
  log "MODEL=$model"
  log "RUNTIME_ROOT=$RUNTIME_ROOT"
  log "CONFIG_PATH=$CONFIG_PATH"
  log "WHEEL=$(find "$PAYLOAD_ROOT/wheel" -maxdepth 1 -name 'family_recorder-*.whl' -print -quit)"
}

command="${1:-preflight}"
case "$command" in
  preflight)
    preflight
    ;;
  install-codex)
    install_codex
    ;;
  codex-login)
    login_codex
    ;;
  codex-device-login)
    login_codex_with_device_code
    ;;
  install)
    install_family_recorder "${2:-large-v3-turbo}"
    ;;
  dry-run)
    dry_run "${2:-large-v3-turbo}"
    ;;
  *)
    fail "未知操作：$command"
    ;;
esac
