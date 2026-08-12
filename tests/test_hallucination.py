from family_recorder.config import DirectionConfig, HallucinationFilterConfig
from family_recorder.direction import SpeechEnergySample, summarize_speech_energy
from family_recorder.hallucination import (
    AdaptiveNoiseFloor,
    acoustic_filter_reason,
    normalize_transcript_text,
    transcription_filter_decision,
)
from family_recorder.metrics import AudioAnalysis
from family_recorder.transcriber import (
    TranscriptionQuality,
    TranscriptionResult,
    TranscriptionSegment,
)


def _silence_energy():
    return summarize_speech_energy(
        [SpeechEnergySample(0, 0, 0, 0, 0)],
        DirectionConfig(),
    )


def _unavailable_energy():
    return summarize_speech_energy([], DirectionConfig(), error="USB unavailable")


def test_hardware_silence_rejects_weak_software_vad_false_positive() -> None:
    analysis = AudioAnalysis(True, -40.8, 4.2, 0.118, 1_000, 0.72, 0.44)

    assert (
        acoustic_filter_reason(
            analysis,
            _silence_energy(),
            HallucinationFilterConfig(),
        )
        == "hallucination_filter:hardware_silence"
    )


def test_hardware_silence_does_not_override_strong_software_evidence() -> None:
    config = HallucinationFilterConfig()
    strong_snr = AudioAnalysis(True, -35.0, 18.0, 0.12, 1_000, 0.75, 0.45)
    sustained_speech = AudioAnalysis(True, -35.0, 6.0, 0.55, 1_000, 0.75, 0.45)

    assert acoustic_filter_reason(strong_snr, _silence_energy(), config) is None
    assert acoustic_filter_reason(sustained_speech, _silence_energy(), config) is None


def test_adaptive_tonal_noise_filter_works_when_hardware_is_unavailable() -> None:
    analysis = AudioAnalysis(True, -41.0, 4.0, 0.15, 1_000, 0.80, 0.50)
    config = HallucinationFilterConfig(low_frequency_filter_enabled=False)

    assert (
        acoustic_filter_reason(
            analysis,
            _unavailable_energy(),
            config,
            noise_floor_dbfs=-42.0,
        )
        == "hallucination_filter:adaptive_noise_floor"
    )


def test_tonal_noise_filter_does_not_need_a_warmed_noise_floor() -> None:
    analysis = AudioAnalysis(True, -41.0, 4.0, 0.15, 1_000, 0.80, 0.50)

    assert (
        acoustic_filter_reason(
            analysis,
            _unavailable_energy(),
            HallucinationFilterConfig(),
        )
        == "hallucination_filter:tonal_noise"
    )


def test_adaptive_noise_floor_requires_enough_samples() -> None:
    config = HallucinationFilterConfig(noise_min_samples=3)
    tracker = AdaptiveNoiseFloor(config)
    analysis = AudioAnalysis(False, -42.0, None, 0.0, 1_000)

    tracker.observe(analysis, _silence_energy(), capture_kept=False)
    tracker.observe(
        AudioAnalysis(False, -40.0, None, 0.0, 1_000),
        _silence_energy(),
        capture_kept=False,
    )
    assert tracker.floor_dbfs is None
    tracker.observe(
        AudioAnalysis(False, -41.0, None, 0.0, 1_000),
        _silence_energy(),
        capture_kept=False,
    )
    assert tracker.floor_dbfs == -41.0


def test_low_whisper_confidence_is_filtered() -> None:
    result = TranscriptionResult(
        "演唱：李宗盛",
        (TranscriptionSegment(0, 4_000, "演唱：李宗盛"),),
        TranscriptionQuality(
            avg_logprob=-0.82,
            low_probability_ratio=0.175,
            compression_ratio=1.9,
            token_count=57,
        ),
    )

    decision = transcription_filter_decision(result, [], HallucinationFilterConfig())

    assert decision.keep is False
    assert decision.reason == "whisper_low_logprob"


def test_repeated_long_text_is_filtered_across_chunks() -> None:
    text = "請不吝點讚訂閱轉發打賞支持明鏡與點點欄目"
    result = TranscriptionResult(
        text,
        (TranscriptionSegment(0, 30_000, text),),
        TranscriptionQuality(avg_logprob=-0.2, low_probability_ratio=0.0),
    )
    normalized = normalize_transcript_text(text)

    first = transcription_filter_decision(result, [], HallucinationFilterConfig())
    second = transcription_filter_decision(result, [normalized], HallucinationFilterConfig())

    assert first.keep is True
    assert second.keep is False
    assert second.reason == "repeated_across_chunks"
    assert second.similar_count == 1


def test_short_repeated_utterance_is_not_suppressed() -> None:
    result = TranscriptionResult(
        "好",
        (TranscriptionSegment(0, 500, "好"),),
        TranscriptionQuality(avg_logprob=-0.1, low_probability_ratio=0.0),
    )

    decision = transcription_filter_decision(result, ["好"], HallucinationFilterConfig())

    assert decision.keep is True
