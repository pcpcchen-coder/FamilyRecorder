from pathlib import Path

import pytest

from family_recorder.config import WhisperConfig
from family_recorder.transcriber import TranscriptionError, WhisperCppTranscriber


def _fake_whisper(tmp_path: Path, exit_code: int = 0) -> Path:
    script = tmp_path / "whisper-cli"
    script.write_text(
        f"""#!/usr/bin/env python3
import pathlib
import sys

if {exit_code}:
    print("fake whisper failure", file=sys.stderr)
    raise SystemExit({exit_code})
base = pathlib.Path(sys.argv[sys.argv.index("-of") + 1])
base.with_suffix(".txt").write_text("  測試  逐字稿。\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_whisper_cli_output_is_read_and_normalized(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    transcriber = WhisperCppTranscriber(
        WhisperConfig(binary_path=_fake_whisper(tmp_path), model_path=model)
    )
    assert transcriber.transcribe(audio) == "測試 逐字稿。"


def test_whisper_cli_error_is_actionable(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    transcriber = WhisperCppTranscriber(
        WhisperConfig(binary_path=_fake_whisper(tmp_path, 9), model_path=model)
    )
    with pytest.raises(TranscriptionError, match="fake whisper failure"):
        transcriber.transcribe(audio)
