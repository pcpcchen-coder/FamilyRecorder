from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from family_recorder.audio import AudioChunk, AudioRecorder, write_wav
from family_recorder.config import AppConfig
from family_recorder.metrics import AudioAnalysis, analyze_audio
from family_recorder.storage import Storage
from family_recorder.transcriber import WhisperCppTranscriber

LOGGER = logging.getLogger(__name__)


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _transcribe_segment(
    config: AppConfig,
    transcriber: WhisperCppTranscriber,
    chunk: AudioChunk,
    audio_path: Path,
    analysis: AudioAnalysis,
    *,
    raise_errors: bool,
) -> None:
    try:
        with Storage(config.storage) as storage:
            try:
                text = transcriber.transcribe(audio_path)
                status = "transcribed" if text else "empty"
                storage.save_segment(
                    chunk,
                    audio_path,
                    analysis,
                    text,
                    status=status,
                )
                if text:
                    LOGGER.info("Transcript stored (%d characters)", len(text))
                else:
                    LOGGER.info("Whisper returned no text")
                if config.storage.delete_audio_after_transcription:
                    audio_path.unlink(missing_ok=True)
            except Exception as exc:
                storage.save_segment(
                    chunk,
                    audio_path,
                    analysis,
                    "",
                    status="failed",
                    error=str(exc)[-2_000:],
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
    transcriber = WhisperCppTranscriber(config.whisper)
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

        processed = 0
        while True:
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
                        chunk = recorder.read_chunk(stream)
                        processed += 1
                        analysis = analyze_audio(chunk.pcm16_mono, chunk.sample_rate, config.vad)
                        LOGGER.info(
                            "Chunk %s rms=%.1f dBFS speech=%.1f%% snr=%s dB overflow=%s",
                            chunk.started_at.isoformat(timespec="seconds"),
                            analysis.rms_dbfs,
                            analysis.speech_ratio * 100,
                            _format_optional(analysis.snr_db),
                            chunk.overflowed,
                        )
                        if not analysis.keep:
                            LOGGER.info("Chunk skipped by silence/VAD gate")
                            if once:
                                return
                            continue

                        audio_path = storage.audio_path_for(chunk.started_at)
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
