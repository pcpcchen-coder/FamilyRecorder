from __future__ import annotations

import statistics
import unicodedata
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher

from family_recorder.config import HallucinationFilterConfig
from family_recorder.direction import SpeechEnergySummary
from family_recorder.metrics import AudioAnalysis
from family_recorder.transcriber import TranscriptionResult


@dataclass(frozen=True)
class TranscriptionFilterDecision:
    keep: bool
    reason: str
    normalized_text: str
    similar_count: int = 0


class AdaptiveNoiseFloor:
    def __init__(self, config: HallucinationFilterConfig) -> None:
        self.config = config
        self._levels: deque[float] = deque(maxlen=config.noise_window_chunks)

    def seed(self, levels: list[float] | tuple[float, ...]) -> None:
        for level in levels[-self.config.noise_window_chunks :]:
            self._append(level)

    def observe(
        self,
        analysis: AudioAnalysis,
        speech_energy: SpeechEnergySummary,
        *,
        capture_kept: bool,
    ) -> None:
        hardware_silence = (
            speech_energy.status == "silence"
            and speech_energy.speech_ratio <= self.config.hardware_silence_max_ratio
        )
        if hardware_silence or not capture_kept:
            self._append(analysis.rms_dbfs)

    def _append(self, level: float) -> None:
        if -100.0 < level <= 0.0:
            self._levels.append(float(level))

    @property
    def floor_dbfs(self) -> float | None:
        if len(self._levels) < self.config.noise_min_samples:
            return None
        return float(statistics.median(self._levels))


def acoustic_filter_reason(
    analysis: AudioAnalysis,
    speech_energy: SpeechEnergySummary,
    config: HallucinationFilterConfig,
    *,
    noise_floor_dbfs: float | None = None,
) -> str | None:
    if not config.enabled:
        return None

    software_evidence_is_weak = (
        analysis.speech_ratio <= config.hardware_silence_max_software_speech_ratio
    )
    snr_is_weak = analysis.snr_db is None or analysis.snr_db <= config.hardware_silence_max_snr_db
    hardware_silence = (
        speech_energy.status == "silence"
        and speech_energy.speech_ratio <= config.hardware_silence_max_ratio
    )
    if (
        config.hardware_silence_guard_enabled
        and hardware_silence
        and software_evidence_is_weak
        and snr_is_weak
    ):
        return "hallucination_filter:hardware_silence"

    tonal_low_frequency_noise = (
        config.low_frequency_filter_enabled
        and analysis.low_frequency_ratio >= config.low_frequency_min_ratio
        and analysis.tonal_energy_ratio >= config.tonal_energy_min_ratio
    )
    if (
        speech_energy.status != "speech"
        and software_evidence_is_weak
        and snr_is_weak
        and tonal_low_frequency_noise
    ):
        return "hallucination_filter:tonal_noise"

    near_noise_floor = (
        noise_floor_dbfs is not None
        and analysis.rms_dbfs <= noise_floor_dbfs + config.noise_margin_db
    )
    if (
        config.adaptive_noise_enabled
        and speech_energy.status != "speech"
        and near_noise_floor
        and software_evidence_is_weak
        and snr_is_weak
    ):
        return "hallucination_filter:adaptive_noise_floor"
    return None


def normalize_transcript_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


def transcription_filter_decision(
    result: TranscriptionResult,
    recent_normalized_texts: list[str] | tuple[str, ...],
    config: HallucinationFilterConfig,
) -> TranscriptionFilterDecision:
    normalized = normalize_transcript_text(result.text)
    if not config.enabled or not result.text.strip():
        return TranscriptionFilterDecision(True, "accepted", normalized)

    quality = result.quality
    if config.whisper_confidence_enabled:
        if (
            quality.no_speech_probability is not None
            and quality.no_speech_probability >= config.no_speech_probability_max
        ):
            return TranscriptionFilterDecision(False, "whisper_no_speech", normalized)
        if quality.avg_logprob is not None and quality.avg_logprob < config.min_avg_logprob:
            return TranscriptionFilterDecision(False, "whisper_low_logprob", normalized)
        if (
            quality.low_probability_ratio is not None
            and quality.low_probability_ratio > config.max_low_probability_ratio
        ):
            return TranscriptionFilterDecision(False, "whisper_low_token_confidence", normalized)
        if (
            quality.compression_ratio is not None
            and quality.compression_ratio > config.max_compression_ratio
        ):
            return TranscriptionFilterDecision(False, "whisper_repetitive_text", normalized)

    if not config.repeat_filter_enabled or len(normalized) < config.min_repeat_text_chars:
        return TranscriptionFilterDecision(True, "accepted", normalized)

    similar_count = 0
    for previous in recent_normalized_texts:
        if len(previous) < config.min_repeat_text_chars:
            continue
        similarity = SequenceMatcher(None, normalized, previous, autojunk=False).ratio()
        if similarity >= config.repeat_similarity_threshold:
            similar_count += 1
    if similar_count >= config.max_repetitions:
        return TranscriptionFilterDecision(
            False,
            "repeated_across_chunks",
            normalized,
            similar_count,
        )
    return TranscriptionFilterDecision(True, "accepted", normalized, similar_count)
