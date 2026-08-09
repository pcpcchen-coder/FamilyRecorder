from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from family_recorder.config import WhisperConfig


class TranscriptionError(RuntimeError):
    """Raised when whisper.cpp cannot produce a transcript."""


class WhisperCppTranscriber:
    def __init__(self, config: WhisperConfig) -> None:
        self.config = config

    def validate(self) -> None:
        if not self.config.binary_path.is_file():
            raise FileNotFoundError(f"whisper-cli not found: {self.config.binary_path}")
        if not self.config.model_path.is_file():
            raise FileNotFoundError(f"Whisper model not found: {self.config.model_path}")

    def transcribe(self, audio_path: Path) -> str:
        self.validate()
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        with tempfile.TemporaryDirectory(prefix="familyrecorder-whisper-") as temp_dir:
            output_base = Path(temp_dir) / "transcript"
            command = [
                str(self.config.binary_path),
                "-m",
                str(self.config.model_path),
                "-f",
                str(audio_path),
                "-l",
                self.config.language,
                "-t",
                str(self.config.threads),
                "-otxt",
                "-of",
                str(output_base),
                "-nt",
                "-np",
            ]
            if self.config.initial_prompt:
                command.extend(["--prompt", self.config.initial_prompt])
            command.extend(self.config.extra_args)

            result = subprocess.run(command, capture_output=True, text=True, check=False)
            output_path = output_base.with_suffix(".txt")
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()[-2_000:]
                raise TranscriptionError(
                    f"whisper-cli exited with {result.returncode}: {detail or 'no diagnostics'}"
                )
            if not output_path.is_file():
                raise TranscriptionError("whisper-cli succeeded but did not create a text output")
            return " ".join(output_path.read_text(encoding="utf-8").split()).strip()
