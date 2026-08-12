from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from family_recorder.audio import (
    AudioChunk,
    AudioRecorder,
    CaptureInterrupted,
    read_wav_pcm16_mono,
    slice_pcm16,
    write_wav,
)
from family_recorder.config import AppConfig
from family_recorder.control import ControlStateError, read_pause_state
from family_recorder.direction import (
    DirectionSampler,
    DirectionSummary,
    SpeechEnergySummary,
    direction_for_interval,
)
from family_recorder.hallucination import (
    AdaptiveNoiseFloor,
    acoustic_filter_reason,
    transcription_filter_decision,
)
from family_recorder.metrics import AudioAnalysis, analyze_audio
from family_recorder.speakers import (
    SpeakerIdentification,
    SpeakerProfileError,
    SpeakerProfileStore,
    identify_speaker,
)
from family_recorder.storage import Storage
from family_recorder.transcriber import WhisperCppTranscriber

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureGateDecision:
    keep: bool
    reason: str
    software_keep: bool
    speech_energy_keep: bool


def decide_capture_gate(
    analysis: AudioAnalysis,
    speech_energy: SpeechEnergySummary,
    config: AppConfig,
    *,
    noise_floor_dbfs: float | None = None,
) -> CaptureGateDecision:
    energy_keep = (
        config.direction.enabled
        and config.direction.speech_energy_enabled
        and speech_energy.status == "speech"
        and speech_energy.speech_ratio >= config.direction.speech_energy_min_ratio
        and analysis.rms_dbfs >= config.direction.speech_energy_min_rms_dbfs
    )
    if analysis.keep:
        filter_reason = acoustic_filter_reason(
            analysis,
            speech_energy,
            config.hallucination_filter,
            noise_floor_dbfs=noise_floor_dbfs,
        )
        if filter_reason:
            return CaptureGateDecision(False, filter_reason, True, energy_keep)
        return CaptureGateDecision(True, "software_vad", True, energy_keep)
    if energy_keep:
        return CaptureGateDecision(True, "xvf3800_speech_energy", False, True)
    if speech_energy.status == "unavailable":
        return CaptureGateDecision(False, "software_vad; speech_energy_unavailable", False, False)
    return CaptureGateDecision(False, "silence", False, False)


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _pause_requested(config: AppConfig) -> bool:
    try:
        return read_pause_state(config.storage.data_dir).paused
    except ControlStateError as exc:
        LOGGER.error("%s; ignoring pause state", exc)
        return False


def _transcribe_segment(
    config: AppConfig,
    transcriber: WhisperCppTranscriber,
    chunk: AudioChunk,
    audio_path: Path,
    analysis: AudioAnalysis,
    direction: DirectionSummary,
    capture_id: int | None,
    *,
    raise_errors: bool,
) -> None:
    try:
        with Storage(config.storage) as storage:
            try:
                result = transcriber.transcribe_detailed(audio_path)
                recent_texts = storage.recent_transcription_texts(
                    chunk.started_at,
                    config.hallucination_filter.repeat_window_seconds,
                )
                filter_decision = transcription_filter_decision(
                    result,
                    recent_texts,
                    config.hallucination_filter,
                )
                quality = result.quality
                audit_decision = (
                    "empty"
                    if not result.segments
                    else "accepted"
                    if filter_decision.keep
                    else "filtered"
                )
                storage.record_transcription_audit(
                    capture_id=capture_id,
                    started_at=chunk.started_at,
                    raw_text=result.text,
                    normalized_text=filter_decision.normalized_text,
                    decision=audit_decision,
                    reason=("empty" if not result.segments else filter_decision.reason),
                    avg_logprob=quality.avg_logprob,
                    no_speech_probability=quality.no_speech_probability,
                    low_probability_ratio=quality.low_probability_ratio,
                    compression_ratio=quality.compression_ratio,
                    token_count=quality.token_count,
                    similar_count=filter_decision.similar_count,
                )
                if result.segments and not filter_decision.keep:
                    storage.save_segment(
                        chunk,
                        audio_path,
                        analysis,
                        "",
                        status="empty",
                        error=f"hallucination_filter:{filter_decision.reason}",
                        direction=direction,
                        capture_id=capture_id,
                    )
                    LOGGER.warning(
                        "Whisper output filtered (%s; avg_logprob=%s; low_p=%s; "
                        "compression=%s; similar=%d)",
                        filter_decision.reason,
                        _format_optional(quality.avg_logprob),
                        _format_optional(quality.low_probability_ratio),
                        _format_optional(quality.compression_ratio),
                        filter_decision.similar_count,
                    )
                    if config.storage.delete_audio_after_transcription:
                        audio_path.unlink(missing_ok=True)
                    return
                if result.segments:
                    pcm16_mono, sample_rate = read_wav_pcm16_mono(audio_path)
                    profiles = []
                    if config.speakers.enabled and config.speakers.members:
                        profile_store = SpeakerProfileStore(config.storage.data_dir)
                        try:
                            profiles = [
                                profile
                                for name in config.speakers.members
                                if (profile := profile_store.load(name)) is not None
                            ]
                        except SpeakerProfileError as exc:
                            LOGGER.error("Speaker profile ignored: %s", exc)
                    maximum_ms = round((chunk.ended_at - chunk.started_at).total_seconds() * 1_000)
                    for transcript_segment in result.segments:
                        start_ms = min(maximum_ms, max(0, transcript_segment.start_ms))
                        end_ms = min(
                            maximum_ms,
                            max(start_ms, transcript_segment.end_ms),
                        )
                        segment_pcm = slice_pcm16(
                            pcm16_mono,
                            sample_rate,
                            start_ms,
                            end_ms,
                        )
                        speaker: SpeakerIdentification | None = None
                        if config.speakers.enabled and profiles:
                            speaker = identify_speaker(
                                segment_pcm,
                                sample_rate,
                                profiles,
                                config.speakers,
                            )
                        segment_direction = direction_for_interval(
                            direction,
                            config.direction,
                            start_ms,
                            end_ms,
                        )
                        segment_chunk = AudioChunk(
                            b"",
                            sample_rate,
                            chunk.started_at + timedelta(milliseconds=start_ms),
                            chunk.started_at + timedelta(milliseconds=end_ms),
                            chunk.overflowed,
                        )
                        storage.save_segment(
                            segment_chunk,
                            audio_path,
                            analysis,
                            transcript_segment.text,
                            speaker=speaker,
                            direction=segment_direction,
                            capture_id=capture_id,
                        )
                        if speaker and speaker.status == "recognized":
                            LOGGER.info(
                                "Approximate speaker at +%.1fs: %s (similarity %.1f%%)",
                                start_ms / 1_000,
                                speaker.label,
                                (speaker.confidence or 0) * 100,
                            )
                    LOGGER.info(
                        "Transcript stored (%d characters in %d timed segments)",
                        len(result.text),
                        len(result.segments),
                    )
                else:
                    storage.save_segment(
                        chunk,
                        audio_path,
                        analysis,
                        "",
                        status="empty",
                        direction=direction,
                        capture_id=capture_id,
                    )
                    LOGGER.info("Whisper returned no text")
                if config.storage.delete_audio_after_transcription:
                    audio_path.unlink(missing_ok=True)
            except Exception as exc:
                storage.record_transcription_audit(
                    capture_id=capture_id,
                    started_at=chunk.started_at,
                    raw_text="",
                    normalized_text="",
                    decision="failed",
                    reason=str(exc)[-2_000:],
                )
                storage.save_segment(
                    chunk,
                    audio_path,
                    analysis,
                    "",
                    status="failed",
                    error=str(exc)[-2_000:],
                    direction=direction,
                    capture_id=capture_id,
                )
                LOGGER.exception("Transcription failed; audio retained at %s", audio_path)
                if raise_errors:
                    raise
    except Exception:
        if raise_errors:
            raise
        LOGGER.exception("Background transcription pipeline failed for %s", audio_path)


def run_listener(config: AppConfig, once: bool = False) -> None:
    recorder = AudioRecorder(config.audio)
    transcriber = WhisperCppTranscriber(config.whisper, config.hallucination_filter)
    transcriber.validate()

    with (
        Storage(config.storage) as storage,
        ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="familyrecorder-whisper",
        ) as transcription_pool,
    ):
        cleanup = storage.cleanup_audio()
        if cleanup.removed_files:
            LOGGER.info(
                "Retention removed %d audio files (%.1f MiB)",
                cleanup.removed_files,
                cleanup.removed_bytes / 1024 / 1024,
            )

        noise_floor = AdaptiveNoiseFloor(config.hallucination_filter)
        noise_floor.seed(
            storage.recent_noise_levels(
                config.hallucination_filter.hardware_silence_max_ratio,
                config.hallucination_filter.noise_window_chunks,
            )
        )

        processed = 0
        pause_was_logged = False
        direction_error_was_logged = False
        speech_energy_error_was_logged = False
        while True:
            try:
                pause_state = read_pause_state(config.storage.data_dir)
            except ControlStateError as exc:
                LOGGER.error("%s; ignoring pause state", exc)
                pause_state = None
            if pause_state is not None and pause_state.paused:
                if not pause_was_logged:
                    LOGGER.info("%s", pause_state.label)
                    pause_was_logged = True
                if once:
                    return
                time.sleep(5)
                continue
            if pause_was_logged:
                LOGGER.info("Recording resumed")
                pause_was_logged = False
            try:
                with recorder.open_stream() as stream:
                    assert recorder.device is not None
                    LOGGER.info(
                        "Listening on [%d] %s at %d Hz (Whisper/VAD target %d Hz)",
                        recorder.device.index,
                        recorder.device.name,
                        recorder.capture_sample_rate,
                        config.audio.sample_rate,
                    )
                    while True:
                        direction_sampler = DirectionSampler(config.direction)
                        direction_sampler.start()
                        try:
                            try:
                                chunk = recorder.read_chunk(
                                    stream,
                                    stop_requested=lambda: _pause_requested(config),
                                )
                            finally:
                                acoustic = direction_sampler.stop_acoustic()
                        except CaptureInterrupted:
                            LOGGER.info("Pause activated; discarded the in-progress chunk")
                            pause_was_logged = True
                            break
                        processed += 1
                        direction = acoustic.direction
                        speech_energy = acoustic.speech_energy
                        analysis = analyze_audio(chunk.pcm16_mono, chunk.sample_rate, config.vad)
                        gate = decide_capture_gate(
                            analysis,
                            speech_energy,
                            config,
                            noise_floor_dbfs=noise_floor.floor_dbfs,
                        )
                        noise_floor.observe(
                            analysis,
                            speech_energy,
                            capture_kept=gate.keep,
                        )
                        LOGGER.info(
                            "Chunk %s rms=%.1f dBFS speech=%.1f%% snr=%s dB "
                            "low=%.1f%% tonal=%.1f%% noise_floor=%s dB overflow=%s",
                            chunk.started_at.isoformat(timespec="seconds"),
                            analysis.rms_dbfs,
                            analysis.speech_ratio * 100,
                            _format_optional(analysis.snr_db),
                            analysis.low_frequency_ratio * 100,
                            analysis.tonal_energy_ratio * 100,
                            _format_optional(noise_floor.floor_dbfs),
                            chunk.overflowed,
                        )
                        if direction.status == "detected":
                            LOGGER.info(
                                "Direction: %s %.0f° (stability %.1f%%, %d speech samples)",
                                direction.label,
                                direction.angle_degrees or 0,
                                (direction.confidence or 0) * 100,
                                direction.speech_sample_count,
                            )
                            direction_error_was_logged = False
                        elif direction.status == "multiple":
                            LOGGER.info(
                                "Direction: multiple (%s)",
                                ", ".join(
                                    f"{cluster.label} {cluster.angle_degrees:.0f}°"
                                    for cluster in direction.clusters[:3]
                                ),
                            )
                            direction_error_was_logged = False
                        elif direction.status == "unavailable" and not direction_error_was_logged:
                            LOGGER.warning("Direction telemetry unavailable: %s", direction.error)
                            direction_error_was_logged = True
                        if speech_energy.status in {"speech", "silence"}:
                            LOGGER.info(
                                "XVF3800 speech energy: speech=%.1f%% auto peak=%.1f "
                                "auto mean=%.1f",
                                speech_energy.speech_ratio * 100,
                                speech_energy.peak_auto_selected or 0,
                                speech_energy.mean_auto_selected or 0,
                            )
                            speech_energy_error_was_logged = False
                        elif (
                            speech_energy.status == "unavailable"
                            and not speech_energy_error_was_logged
                        ):
                            LOGGER.warning(
                                "XVF3800 speech-energy telemetry unavailable: %s",
                                speech_energy.error,
                            )
                            speech_energy_error_was_logged = True

                        audio_path = storage.audio_path_for(chunk.started_at) if gate.keep else None
                        capture_id = storage.save_capture(
                            chunk,
                            analysis,
                            acoustic,
                            combined_keep=gate.keep,
                            gate_reason=gate.reason,
                            audio_path=audio_path,
                        )
                        if not gate.keep:
                            LOGGER.info("Chunk skipped by gate: %s", gate.reason)
                            if once:
                                return
                            continue

                        assert audio_path is not None
                        if gate.reason == "xvf3800_speech_energy":
                            LOGGER.info("Chunk retained by XVF3800 speech-energy evidence")
                        write_wav(audio_path, chunk.pcm16_mono, chunk.sample_rate)
                        # The worker receives only timing metadata, not the PCM
                        # payload, so a temporary transcription slowdown cannot
                        # grow the listener's memory use by roughly 1 MiB/chunk.
                        stored_chunk = AudioChunk(
                            b"",
                            chunk.sample_rate,
                            chunk.started_at,
                            chunk.ended_at,
                            chunk.overflowed,
                        )
                        transcription = transcription_pool.submit(
                            _transcribe_segment,
                            config,
                            transcriber,
                            stored_chunk,
                            audio_path,
                            analysis,
                            direction,
                            capture_id,
                            raise_errors=once,
                        )

                        if processed % 120 == 0:
                            storage.cleanup_audio()
                        if once:
                            transcription.result()
                            return
            except KeyboardInterrupt:
                LOGGER.info("Listener stopped")
                return
            except Exception as exc:
                if once:
                    raise
                LOGGER.error(
                    "%s; retrying in %d seconds",
                    exc,
                    config.audio.retry_seconds,
                )
                time.sleep(config.audio.retry_seconds)


def validate_runtime_paths(config: AppConfig) -> list[tuple[str, Path, bool]]:
    return [
        ("whisper-cli", config.whisper.binary_path, config.whisper.binary_path.is_file()),
        ("Whisper model", config.whisper.model_path, config.whisper.model_path.is_file()),
        ("data directory", config.storage.data_dir, config.storage.data_dir.exists()),
    ]
