import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from family_recorder.audio import AudioChunk, write_wav
from family_recorder.config import DirectionConfig, StorageConfig
from family_recorder.direction import DirectionSample, summarize_direction
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
    } <= columns


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
