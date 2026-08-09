#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "DMG builds require macOS." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "This DMG target is Apple Silicon (arm64)." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$REPO_ROOT/pyproject.toml" | head -1)"
[[ -n "$VERSION" ]] || {
  echo "Unable to read project version." >&2
  exit 1
}

PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
BUILD_ROOT="$(mktemp -d -t familyrecorder-dmg-build)"
STAGE_ROOT="$BUILD_ROOT/stage"
APP_ROOT="$STAGE_ROOT/安裝 FamilyRecorder.app"
CONTENTS="$APP_ROOT/Contents"
RESOURCES="$CONTENTS/Resources"
PAYLOAD="$RESOURCES/FamilyRecorderPayload"
DIST_ROOT="$REPO_ROOT/dist"
DMG_PATH="$DIST_ROOT/FamilyRecorder-$VERSION-arm64.dmg"
CHECKSUM_PATH="$DMG_PATH.sha256"
SIGN_IDENTITY="${SIGN_IDENTITY:--}"
trap 'rm -rf "$BUILD_ROOT"' EXIT
rm -rf "$REPO_ROOT/build/lib"
find "$REPO_ROOT/build" -maxdepth 1 -type d -name 'bdist.*' -exec rm -rf {} +
mkdir -p "$CONTENTS/MacOS" "$PAYLOAD/wheel" "$DIST_ROOT"
rm -f "$DMG_PATH" "$CHECKSUM_PATH"

echo "Building FamilyRecorder wheel…"
"$PYTHON" -m build --wheel --outdir "$PAYLOAD/wheel" "$REPO_ROOT"

echo "Compiling native installer…"
xcrun swiftc -O -parse-as-library -swift-version 5 \
  -target arm64-apple-macos13.0 -framework AppKit \
  "$REPO_ROOT/packaging/FamilyRecorderInstaller.swift" \
  -o "$CONTENTS/MacOS/FamilyRecorderInstaller"
install -m 644 "$REPO_ROOT/packaging/InstallerInfo.plist" "$CONTENTS/Info.plist"
install -m 755 "$REPO_ROOT/packaging/install_payload.sh" "$RESOURCES/install_payload.sh"

install -m 644 "$REPO_ROOT/config.example.yaml" "$PAYLOAD/config.example.yaml"
cp -R "$REPO_ROOT/launchd" "$PAYLOAD/launchd"
cp -R "$REPO_ROOT/menubar" "$PAYLOAD/menubar"
mkdir -p "$PAYLOAD/scripts"
for script in \
  install_mac.sh \
  install_launchd.sh \
  install_daily_summary.sh \
  install_menubar.sh \
  uninstall_launchd.sh; do
  install -m 755 "$REPO_ROOT/scripts/$script" "$PAYLOAD/scripts/$script"
done
install -m 644 "$REPO_ROOT/packaging/開始安裝前請先看.txt" \
  "$STAGE_ROOT/開始安裝前請先看.txt"

plutil -lint "$CONTENTS/Info.plist"
xattr -cr "$APP_ROOT"
codesign --force --deep --options runtime --sign "$SIGN_IDENTITY" "$APP_ROOT"
codesign --verify --deep --strict --verbose=2 "$APP_ROOT"

echo "Creating compressed DMG…"
hdiutil create \
  -volname "FamilyRecorder $VERSION" \
  -srcfolder "$STAGE_ROOT" \
  -format UDZO \
  -imagekey zlib-level=9 \
  -ov \
  "$DMG_PATH"

shasum -a 256 "$DMG_PATH" > "$CHECKSUM_PATH"
echo "DMG: $DMG_PATH"
echo "SHA-256: $CHECKSUM_PATH"
