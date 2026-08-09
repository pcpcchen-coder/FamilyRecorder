#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "FamilyRecorder installer supports macOS only." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh and rerun this script." >&2
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Warning: this installer is tuned for Apple Silicon (arm64)." >&2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_ROOT="${FAMILYRECORDER_RUNTIME_ROOT:-$HOME/Library/Application Support/FamilyRecorder}"
CONFIG_PATH="${FAMILYRECORDER_CONFIG:-$HOME/.config/familyrecorder/config.yaml}"
WHISPER_VERSION="${WHISPER_CPP_VERSION:-v1.8.1}"
WHISPER_MODEL="${WHISPER_MODEL:-large-v3-turbo}"

brew install python@3.12 portaudio cmake git

PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
mkdir -p "$RUNTIME_ROOT" "$(dirname "$CONFIG_PATH")"
"$PYTHON" -m venv "$RUNTIME_ROOT/venv"
"$RUNTIME_ROOT/venv/bin/python" -m pip install --upgrade pip
"$RUNTIME_ROOT/venv/bin/pip" install "$REPO_ROOT"

WHISPER_ROOT="$RUNTIME_ROOT/whisper.cpp"
if [[ ! -d "$WHISPER_ROOT/.git" ]]; then
  git clone --branch "$WHISPER_VERSION" --depth 1 \
    https://github.com/ggml-org/whisper.cpp.git "$WHISPER_ROOT"
else
  echo "Preserving existing whisper.cpp checkout: $WHISPER_ROOT"
fi

cmake -S "$WHISPER_ROOT" -B "$WHISPER_ROOT/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_METAL=ON
cmake --build "$WHISPER_ROOT/build" --config Release -j "$(sysctl -n hw.logicalcpu)"

MODEL_PATH="$WHISPER_ROOT/models/ggml-$WHISPER_MODEL.bin"
if [[ ! -f "$MODEL_PATH" ]]; then
  "$WHISPER_ROOT/models/download-ggml-model.sh" "$WHISPER_MODEL"
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  install -m 600 "$REPO_ROOT/config.example.yaml" "$CONFIG_PATH"
  echo "Created configuration: $CONFIG_PATH"
else
  echo "Preserving existing configuration: $CONFIG_PATH"
fi

echo
echo "Installation complete. Next run:"
echo "  $RUNTIME_ROOT/venv/bin/family-recorder --config $CONFIG_PATH doctor"
echo "Then follow README.md to grant Microphone access and run a one-chunk test."
