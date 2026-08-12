import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from family_recorder.audio import AudioChunk, write_wav
from family_recorder.config import DirectionConfig, StorageConfig
from family_recorder.direction import (
    AcousticCapture,
    AcousticSample,
    DirectionSample,
    SpeechEnergySample,
    summarize_direction,
    summarize_speech_energy,
)
from family_recorder.metrics import AudioAnalysis
from family_recorder.speakers import SpeakerIdentification
from family_recorder.storage import Storage


def test_segment_is_written_to_markdown_and_sqlite(tmp_path: Path) -> None:
    started = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)
    chunk = AudioChunk(b"\0" * 320, 16_000, started, started + timedelta(seconds=30))
    analysis = AudioAnalysis(True, -20.0, 12.5, 0.7, 100)
    config = StorageConfig(data_dir=tmp_path)

    with Storage(config) as storage:
        assert (tmp_path / ".familyrecorder-data").is_file()
        audio_path = storage.audio_path_for(started)
        write_wav(audio_path, chunk.pcm16_mono, chunk.sample_rate)
        row_id = storage.save_segment(chunk, audio_path, analysis, "明天記得拿包裹。")
        transcript = storage.transcript_path_for(started.date()).read_text(encoding="utf-8")
        assert "12:30:00" in transcript
        assert "明天記得拿包裹。" in transcript
        row = storage.connection.execute(
            "select id, status, text, snr_db from segments where id = ?", (row_id,)
        ).fetchone()
        assert row == (row_id, "transcribed", "明天記得拿包裹。", 12.5)


def test_retention_only_removes_expired_wav(tmp_path: Path) -> None:
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    config = StorageConfig(data_dir=tmp_path, keep_audio_days=7)
    with Storage(config) as storage:
        old = storage.audio_dir / "2026-07-01" / "old.wav"
        new = storage.audio_dir / "2026-08-09" / "new.wav"
        write_wav(old, b"\0" * 320, 16_000)
        write_wav(new, b"\0" * 320, 16_000)
        old_time = (now - timedelta(days=8)).timestamp()
        os.utime(old, (old_time, old_time))
        result = storage.cleanup_audio(now)
        assert result.removed_files == 1
        assert not old.exists()
        assert new.exists()
        assert storage.database_path.exists()

    with sqlite3.connect(tmp_path / "listener.sqlite3") as connection:
        assert connection.execute("pragma integrity_check").fetchone() == ("ok",)


def test_segment_stores_approximate_speaker_label(tmp_path: Path) -> None:
    started = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)
    chunk = AudioChunk(b"\0" * 320, 16_000, started, started + timedelta(seconds=30))
    analysis = AudioAnalysis(True, -20.0, 12.5, 0.7, 100)
    speaker = SpeakerIdentification("家人二", 0.87, "recognized", 5, 4)

    with Storage(StorageConfig(data_dir=tmp_path)) as storage:
        audio_path = storage.audio_path_for(started)
        row_id = storage.save_segment(
            chunk,
            audio_path,
            analysis,
            "明天記得拿包裹。",
            speaker=speaker,
        )
        transcript = storage.transcript_path_for(started.date()).read_text(encoding="utf-8")
        assert "可能：家人二（87%）" in transcript
        row = storage.connection.execute(
            "select speaker_name, speaker_confidence, speaker_status from segments where id = ?",
            (row_id,),
        ).fetchone()
        assert row == ("家人二", 0.87, "recognized")


def test_existing_database_gets_speaker_columns(tmp_path: Path) -> None:
    database = tmp_path / "listener.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE segments (
                id INTEGER PRIMARY KEY, transcript_date TEXT, started_at TEXT, ended_at TEXT,
                audio_path TEXT, text TEXT, rms_dbfs REAL, snr_db REAL, speech_ratio REAL,
                status TEXT, error TEXT, created_at TEXT
            )
            """
        )

    with Storage(StorageConfig(data_dir=tmp_path)) as storage:
        columns = {
            row[1] for row in storage.connection.execute("pragma table_info(segments)").fetchall()
        }
    assert {
        "speaker_name",
        "speaker_confidence",
        "speaker_status",
        "direction_angle_deg",
        "direction_label",
        "direction_status",
        "direction_clusters_json",
        "capture_id",
    } <= columns


def test_capture_stores_speech_energy_time_series_even_when_gate_skips_audio(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)
    chunk = AudioChunk(b"\0" * 320, 16_000, started, started + timedelta(seconds=1))
    analysis = AudioAnalysis(False, -70.0, None, 0.0, 33)
    config = DirectionConfig(min_speech_samples=1)
    direction = summarize_direction([DirectionSample(0, 90, False)], config)
    energy_samples = [
        SpeechEnergySample(0, 0, 0, 0, 0),
        SpeechEnergySample(250, 100, 200, 300, 300),
    ]
    acoustic = AcousticCapture(
        direction,
        summarize_speech_energy(energy_samples, config),
        (
            AcousticSample(0, 90, False, 0, 0, 0, 0),
            AcousticSample(250, 91, True, 100, 200, 300, 300),
        ),
    )

    with Storage(StorageConfig(data_dir=tmp_path)) as storage:
        capture_id = storage.save_capture(
            chunk,
            analysis,
            acoustic,
            combined_keep=False,
            gate_reason="silence",
            audio_path=None,
        )
        capture = storage.connection.execute(
            "select audio_path, hardware_speech_ratio, combined_keep, gate_reason "
            "from captures where id = ?",
            (capture_id,),
        ).fetchone()
        samples = storage.connection.execute(
            "select offset_ms, raw_angle_deg, auto_selected_beam "
            "from acoustic_samples where capture_id = ? order by offset_ms",
            (capture_id,),
        ).fetchall()

    assert capture == (None, 0.5, 0, "silence")
    assert samples == [(0, 90.0, 0.0), (250, 91.0, 300.0)]


def test_transcription_audit_persists_filter_evidence_and_recent_text(tmp_path: Path) -> None:
    started = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)
    chunk = AudioChunk(b"\0" * 320, 16_000, started, started + timedelta(seconds=1))
    analysis = AudioAnalysis(True, -40.0, 4.0, 0.12, 33)
    direction_config = DirectionConfig()
    acoustic = AcousticCapture(
        summarize_direction([], direction_config),
        summarize_speech_energy(
            [SpeechEnergySample(0, 0, 0, 0, 0)],
            direction_config,
        ),
        (),
    )

    with Storage(StorageConfig(data_dir=tmp_path)) as storage:
        capture_id = storage.save_capture(
            chunk,
            analysis,
            acoustic,
            combined_keep=True,
            gate_reason="software_vad",
            audio_path=tmp_path / "noise.wav",
        )
        storage.record_transcription_audit(
            capture_id=capture_id,
            started_at=started,
            raw_text="請不吝點讚訂閱",
            normalized_text="請不吝點讚訂閱",
            decision="filtered",
            reason="repeated_across_chunks",
            avg_logprob=-0.82,
            low_probability_ratio=0.175,
            compression_ratio=1.9,
            token_count=57,
            similar_count=2,
        )
        recent = storage.recent_transcription_texts(
            started + timedelta(seconds=30),
            300,
        )
        row = storage.connection.execute(
            "select decision, reason, avg_logprob, similar_count "
            "from transcription_audits where capture_id = ?",
            (capture_id,),
        ).fetchone()
        stats = storage.hallucination_filter_stats(started.date())

    assert recent == ["請不吝點讚訂閱"]
    assert row == ("filtered", "repeated_across_chunks", -0.82, 2)
    assert stats == {"acoustic": 0, "transcription": 1, "total": 1}


def test_segment_stores_direction_summary_and_samples(tmp_path: Path) -> None:
    started = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)
    chunk = AudioChunk(b"\0" * 320, 16_000, started, started + timedelta(seconds=2))
    analysis = AudioAnalysis(True, -20.0, 12.5, 0.7, 100)
    direction = summarize_direction(
        [
            DirectionSample(0, 88, True),
            DirectionSample(250, 90, True),
            DirectionSample(500, 92, True),
        ],
        DirectionConfig(min_speech_samples=2),
    )

    with Storage(StorageConfig(data_dir=tmp_path)) as storage:
        audio_path = storage.audio_path_for(started)
        row_id = storage.save_segment(
            chunk,
            audio_path,
            analysis,
            "這是左邊的人說的。",
            direction=direction,
        )
        transcript = storage.transcript_path_for(started.date()).read_text(encoding="utf-8")
        assert "方向：左側 90°" in transcript
        row = storage.connection.execute(
            """
            select direction_raw_angle_deg, direction_angle_deg, direction_label,
                   direction_status, direction_speech_samples, direction_total_samples
            from segments where id = ?
            """,
            (row_id,),
        ).fetchone()
        assert row == (90.0, 90.0, "左側", "detected", 3, 3)
        samples = storage.connection.execute(
            "select offset_ms, raw_angle_deg, speech_detected from direction_samples "
            "where segment_id = ? order by offset_ms",
            (row_id,),
        ).fetchall()
        assert samples == [(0, 88.0, 1), (250, 90.0, 1), (500, 92.0, 1)]


def test_calendar_candidates_are_pending_until_confirmed(tmp_path: Path) -> None:
    target = datetime(2026, 8, 9, tzinfo=UTC).date()
    with Storage(StorageConfig(data_dir=tmp_path)) as storage:
        storage.replace_pending_calendar_candidates(
            target,
            [
                {
                    "title": "學校說明會",
                    "starts_at": "2026-08-12T19:00:00+08:00",
                    "ends_at": "2026-08-12T20:00:00+08:00",
                    "all_day": False,
                    "notes": "逐字稿明確提到",
                    "member_name": "陳樂融",
                    "suggested_calendar_id": "school-id",
                }
            ],
        )
        pending = storage.pending_calendar_candidates()
        assert len(pending) == 1
        assert pending[0].suggested_calendar_id == "school-id"
        assert storage.mark_calendar_candidate(
            pending[0].id, "created", external_event_id="event-123"
        )
        assert storage.pending_calendar_candidates() == []
