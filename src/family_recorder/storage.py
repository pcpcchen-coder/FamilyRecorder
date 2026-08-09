from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from family_recorder.audio import AudioChunk
from family_recorder.config import StorageConfig
from family_recorder.metrics import AudioAnalysis
from family_recorder.speakers import SpeakerIdentification

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    rms_dbfs REAL NOT NULL,
    snr_db REAL,
    speech_ratio REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('transcribed', 'empty', 'failed')),
    error TEXT,
    speaker_name TEXT,
    speaker_confidence REAL,
    speaker_status TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_segments_date_started
ON segments(transcript_date, started_at);

CREATE INDEX IF NOT EXISTS idx_segments_status
ON segments(status);

CREATE TABLE IF NOT EXISTS summaries (
    summary_date TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class CleanupResult:
    removed_files: int
    removed_bytes: int


class Storage:
    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self.root = config.data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".familyrecorder-data").touch(mode=0o600, exist_ok=True)
        self.audio_dir = self.root / "audio"
        self.transcript_dir = self.root / "transcripts"
        self.summary_dir = self.root / "summaries"
        self.log_dir = self.root / "logs"
        for directory in (self.audio_dir, self.transcript_dir, self.summary_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "listener.sqlite3"
        self.connection = sqlite3.connect(self.database_path)
        self.connection.executescript(SCHEMA)
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(segments)").fetchall()
        }
        additions = {
            "speaker_name": "TEXT",
            "speaker_confidence": "REAL",
            "speaker_status": "TEXT",
        }
        with self.connection:
            for name, declaration in additions.items():
                if name not in columns:
                    self.connection.execute(f"ALTER TABLE segments ADD COLUMN {name} {declaration}")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def audio_path_for(self, started_at: datetime) -> Path:
        day_dir = self.audio_dir / started_at.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"{started_at:%H%M%S_%f}.wav"

    def transcript_path_for(self, target_date: date) -> Path:
        return self.transcript_dir / f"{target_date.isoformat()}.md"

    def summary_path_for(self, target_date: date) -> Path:
        return self.summary_dir / f"{target_date.isoformat()}.md"

    def save_segment(
        self,
        chunk: AudioChunk,
        audio_path: Path,
        analysis: AudioAnalysis,
        text: str,
        status: str = "transcribed",
        error: str | None = None,
        speaker: SpeakerIdentification | None = None,
    ) -> int:
        if status == "transcribed" and text:
            transcript_path = self.transcript_path_for(chunk.started_at.date())
            new_file = not transcript_path.exists()
            with transcript_path.open("a", encoding="utf-8") as transcript:
                if new_file:
                    transcript.write(
                        f"# FamilyRecorder transcript — {chunk.started_at:%Y-%m-%d}\n\n"
                    )
                speaker_label = ""
                if speaker and speaker.status == "recognized" and speaker.label:
                    confidence = (
                        f"（{speaker.confidence:.0%}）" if speaker.confidence is not None else ""
                    )
                    speaker_label = f" — 可能：{speaker.label}{confidence}"
                elif speaker and speaker.status == "mixed":
                    speaker_label = " — 人別：可能多人"
                elif speaker and speaker.status == "uncertain":
                    speaker_label = " — 人別：不確定"
                transcript.write(
                    f"### {chunk.started_at:%H:%M:%S}–{chunk.ended_at:%H:%M:%S}"
                    f"{speaker_label}\n\n{text}\n\n"
                )

        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO segments (
                    transcript_date, started_at, ended_at, audio_path, text,
                    rms_dbfs, snr_db, speech_ratio, status, error,
                    speaker_name, speaker_confidence, speaker_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.started_at.date().isoformat(),
                    chunk.started_at.isoformat(),
                    chunk.ended_at.isoformat(),
                    str(audio_path),
                    text,
                    analysis.rms_dbfs,
                    analysis.snr_db,
                    analysis.speech_ratio,
                    status,
                    error,
                    speaker.label if speaker else None,
                    speaker.confidence if speaker else None,
                    speaker.status if speaker else None,
                    datetime.now().astimezone().isoformat(),
                ),
            )
        return int(cursor.lastrowid)

    def record_summary(self, target_date: date, path: Path, model: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO summaries(summary_date, path, model, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(summary_date) DO UPDATE SET
                    path = excluded.path,
                    model = excluded.model,
                    created_at = excluded.created_at
                """,
                (
                    target_date.isoformat(),
                    str(path),
                    model,
                    datetime.now().astimezone().isoformat(),
                ),
            )

    def cleanup_audio(self, now: datetime | None = None) -> CleanupResult:
        now = now or datetime.now().astimezone()
        cutoff = now - timedelta(days=self.config.keep_audio_days)
        removed_files = 0
        removed_bytes = 0
        for path in self.audio_dir.glob("*/*.wav"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=now.tzinfo)
            if modified >= cutoff:
                continue
            removed_bytes += path.stat().st_size
            path.unlink()
            removed_files += 1
        for directory in sorted(self.audio_dir.glob("*"), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        return CleanupResult(removed_files, removed_bytes)
