from __future__ import annotations

import json
import math
import subprocess
import tempfile
import unicodedata
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from family_recorder.config import HallucinationFilterConfig, WhisperConfig


class TranscriptionError(RuntimeError):
    """Raised when whisper.cpp cannot produce a transcript."""


@dataclass(frozen=True)
class TranscriptionSegment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class TranscriptionQuality:
    avg_logprob: float | None = None
    no_speech_probability: float | None = None
    low_probability_ratio: float | None = None
    compression_ratio: float | None = None
    token_count: int = 0


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: tuple[TranscriptionSegment, ...]
    quality: TranscriptionQuality = field(default_factory=TranscriptionQuality)


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
    def __init__(
        self,
        config: WhisperConfig,
        hallucination_filter: HallucinationFilterConfig | None = None,
    ) -> None:
        self.config = config
        self.hallucination_filter = hallucination_filter or HallucinationFilterConfig()

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
            output_json_flag = "-ojf" if self.hallucination_filter.enabled else "-oj"
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
                output_json_flag,
                "-of",
                str(output_base),
                "-np",
            ]
            if self.hallucination_filter.enabled:
                command.extend(
                    [
                        "-nth",
                        str(self.hallucination_filter.no_speech_probability_max),
                        "-lpt",
                        str(self.hallucination_filter.min_avg_logprob),
                    ]
                )
                if self.hallucination_filter.suppress_non_speech_tokens:
                    command.append("-sns")
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
                # whisper.cpp full JSON may expose individual UTF-8 token bytes
                # that are not independently valid text. Segment text remains
                # valid, while replacement decoding lets us retain probabilities.
                payload = json.loads(output_path.read_bytes().decode("utf-8", errors="replace"))
                raw_segments = payload.get("transcription", [])
                segments: list[TranscriptionSegment] = []
                token_probabilities: list[float] = []
                reported_logprobs: list[float] = []
                no_speech_probabilities: list[float] = []
                for raw in raw_segments:
                    offsets = raw.get("offsets", {})
                    start_ms = max(0, int(offsets.get("from", 0)))
                    end_ms = max(start_ms, int(offsets.get("to", start_ms)))
                    text = " ".join(str(raw.get("text", "")).split()).strip()
                    text = correct_common_terms(text, self.config.common_terms)
                    if text:
                        segments.append(TranscriptionSegment(start_ms, end_ms, text))
                    raw_logprob = raw.get("avg_logprob")
                    if isinstance(raw_logprob, (int, float)):
                        reported_logprobs.append(float(raw_logprob))
                    raw_no_speech = raw.get("no_speech_prob", raw.get("no_speech_probability"))
                    if isinstance(raw_no_speech, (int, float)):
                        no_speech_probabilities.append(float(raw_no_speech))
                    for token in raw.get("tokens", []):
                        token_label = str(token.get("text", ""))
                        probability = token.get("p")
                        if isinstance(probability, (int, float)) and not token_label.startswith(
                            "[_"
                        ):
                            token_probabilities.append(max(1e-9, min(1.0, float(probability))))
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise TranscriptionError(f"Unable to parse whisper-cli JSON output: {exc}") from exc
            combined_text = " ".join(segment.text for segment in segments).strip()
            if reported_logprobs:
                avg_logprob = sum(reported_logprobs) / len(reported_logprobs)
            elif token_probabilities:
                avg_logprob = sum(math.log(value) for value in token_probabilities) / len(
                    token_probabilities
                )
            else:
                avg_logprob = None
            low_probability_ratio = None
            if token_probabilities:
                low_probability_ratio = sum(
                    value < self.hallucination_filter.low_probability_threshold
                    for value in token_probabilities
                ) / len(token_probabilities)
            no_speech_probability = None
            if no_speech_probabilities:
                no_speech_probability = max(no_speech_probabilities)
            elif isinstance(payload.get("no_speech_prob"), (int, float)):
                no_speech_probability = float(payload["no_speech_prob"])
            encoded_text = combined_text.encode("utf-8")
            compression_ratio = (
                len(encoded_text) / max(1, len(zlib.compress(encoded_text)))
                if encoded_text
                else None
            )
            return TranscriptionResult(
                combined_text,
                tuple(segments),
                TranscriptionQuality(
                    avg_logprob=avg_logprob,
                    no_speech_probability=no_speech_probability,
                    low_probability_ratio=low_probability_ratio,
                    compression_ratio=compression_ratio,
                    token_count=len(token_probabilities),
                ),
            )
