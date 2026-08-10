from __future__ import annotations

import json
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from family_recorder.config import WhisperConfig


class TranscriptionError(RuntimeError):
    """Raised when whisper.cpp cannot produce a transcript."""


@dataclass(frozen=True)
class TranscriptionSegment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: tuple[TranscriptionSegment, ...]


def _wordish(value: str) -> bool:
    return bool(value) and all(
        not character.isspace() and not unicodedata.category(character).startswith("P")
        for character in value
    )


def correct_common_terms(text: str, terms: tuple[str, ...]) -> str:
    """Correct an unambiguous same-length, one-character near miss.

    Short terms and ambiguous matches are intentionally left unchanged. The
    Whisper prompt remains the primary hint; this pass only catches conservative
    mistakes such as ``陳樂榮`` when ``陳樂融`` is the sole configured candidate.
    """
    replacements: list[tuple[int, int, str]] = []
    occupied: set[int] = set()
    by_length: dict[int, tuple[str, ...]] = {}
    for term in terms:
        if len(term) >= 3 and _wordish(term):
            by_length.setdefault(len(term), tuple())
            by_length[len(term)] += (term,)

    for length in sorted(by_length, reverse=True):
        candidates = by_length[length]
        for start in range(len(text) - length + 1):
            end = start + length
            if any(index in occupied for index in range(start, end)):
                continue
            value = text[start:end]
            if not _wordish(value) or value in candidates:
                continue
            matches = [
                term
                for term in candidates
                if sum(left != right for left, right in zip(value, term, strict=True)) == 1
            ]
            if len(matches) == 1:
                replacements.append((start, end, matches[0]))
                occupied.update(range(start, end))

    corrected = text
    for start, end, replacement in sorted(replacements, reverse=True):
        corrected = corrected[:start] + replacement + corrected[end:]
    return corrected


class WhisperCppTranscriber:
    def __init__(self, config: WhisperConfig) -> None:
        self.config = config

    def validate(self) -> None:
        if not self.config.binary_path.is_file():
            raise FileNotFoundError(f"whisper-cli not found: {self.config.binary_path}")
        if not self.config.model_path.is_file():
            raise FileNotFoundError(f"Whisper model not found: {self.config.model_path}")

    def transcribe(self, audio_path: Path) -> str:
        return self.transcribe_detailed(audio_path).text

    def transcribe_detailed(self, audio_path: Path) -> TranscriptionResult:
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
                "-oj",
                "-of",
                str(output_base),
                "-np",
            ]
            prompt_parts = (
                [self.config.initial_prompt.strip()] if self.config.initial_prompt else []
            )
            if self.config.common_terms:
                prompt_parts.append(
                    "以下常用字詞請優先使用正確寫法：" + "、".join(self.config.common_terms) + "。"
                )
            if prompt_parts:
                command.extend(["--prompt", " ".join(prompt_parts)])
            command.extend(self.config.extra_args)

            result = subprocess.run(command, capture_output=True, text=True, check=False)
            output_path = output_base.with_suffix(".json")
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()[-2_000:]
                raise TranscriptionError(
                    f"whisper-cli exited with {result.returncode}: {detail or 'no diagnostics'}"
                )
            if not output_path.is_file():
                raise TranscriptionError("whisper-cli succeeded but did not create a JSON output")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                raw_segments = payload.get("transcription", [])
                segments: list[TranscriptionSegment] = []
                for raw in raw_segments:
                    offsets = raw.get("offsets", {})
                    start_ms = max(0, int(offsets.get("from", 0)))
                    end_ms = max(start_ms, int(offsets.get("to", start_ms)))
                    text = " ".join(str(raw.get("text", "")).split()).strip()
                    text = correct_common_terms(text, self.config.common_terms)
                    if text:
                        segments.append(TranscriptionSegment(start_ms, end_ms, text))
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise TranscriptionError(f"Unable to parse whisper-cli JSON output: {exc}") from exc
            return TranscriptionResult(
                " ".join(segment.text for segment in segments).strip(),
                tuple(segments),
            )
