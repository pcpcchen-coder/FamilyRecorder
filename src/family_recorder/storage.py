from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from family_recorder.audio import AudioChunk
from family_recorder.config import StorageConfig
from family_recorder.direction import DirectionSummary
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
    direction_raw_angle_deg REAL,
    direction_angle_deg REAL,
    direction_label TEXT,
    direction_confidence REAL,
    direction_status TEXT,
    direction_spread_deg REAL,
    direction_speech_samples INTEGER,
    direction_total_samples INTEGER,
    direction_clusters_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_segments_date_started
ON segments(transcript_date, started_at);

CREATE INDEX IF NOT EXISTS idx_segments_status
ON segments(status);

CREATE TABLE IF NOT EXISTS direction_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    offset_ms INTEGER NOT NULL,
    raw_angle_deg REAL NOT NULL,
    speech_detected INTEGER NOT NULL CHECK(speech_detected IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_direction_samples_segment_offset
ON direction_samples(segment_id, offset_ms);

CREATE TABLE IF NOT EXISTS summaries (
    summary_date TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_date TEXT NOT NULL,
    title TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    all_day INTEGER NOT NULL CHECK(all_day IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    member_name TEXT NOT NULL DEFAULT '',
    suggested_calendar_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('pending', 'created', 'dismissed', 'failed')),
    external_event_id TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(summary_date, title, starts_at, member_name)
);

CREATE INDEX IF NOT EXISTS idx_calendar_candidates_status_start
ON calendar_candidates(status, starts_at);
"""


@dataclass(frozen=True)
class CleanupResult:
    removed_files: int
    removed_bytes: int


@dataclass(frozen=True)
class CalendarCandidate:
    id: int
    summary_date: str
    title: str
    starts_at: str
    ends_at: str
    all_day: bool
    notes: str
    member_name: str
    suggested_calendar_id: str
    status: str


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
            "direction_raw_angle_deg": "REAL",
            "direction_angle_deg": "REAL",
            "direction_label": "TEXT",
            "direction_confidence": "REAL",
            "direction_status": "TEXT",
            "direction_spread_deg": "REAL",
            "direction_speech_samples": "INTEGER",
            "direction_total_samples": "INTEGER",
            "direction_clusters_json": "TEXT",
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
        direction: DirectionSummary | None = None,
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
                direction_label = ""
                if direction and direction.status == "detected" and direction.label:
                    stability = (
                        f"；穩定度 {direction.confidence:.0%}"
                        if direction.confidence is not None
                        else ""
                    )
                    direction_label = (
                        f" — 方向：{direction.label} {direction.angle_degrees:.0f}°{stability}"
                    )
                elif direction and direction.status == "multiple":
                    clusters = "、".join(
                        f"{cluster.label} {cluster.angle_degrees:.0f}°"
                        for cluster in direction.clusters[:3]
                    )
                    direction_label = f" — 方向：多個（{clusters}）"
                elif direction and direction.status == "uncertain":
                    direction_label = " — 方向：不確定"
                elif direction and direction.status == "unavailable":
                    direction_label = " — 方向：無法讀取"
                transcript.write(
                    f"### {chunk.started_at:%H:%M:%S}–{chunk.ended_at:%H:%M:%S}"
                    f"{speaker_label}{direction_label}\n\n{text}\n\n"
                )

        clusters_json = None
        if direction:
            clusters_json = json.dumps(
                [
                    {
                        "raw_angle_deg": round(cluster.raw_angle_degrees, 3),
                        "angle_deg": round(cluster.angle_degrees, 3),
                        "label": cluster.label,
                        "sample_count": cluster.sample_count,
                        "ratio": round(cluster.ratio, 6),
                    }
                    for cluster in direction.clusters
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO segments (
                    transcript_date, started_at, ended_at, audio_path, text,
                    rms_dbfs, snr_db, speech_ratio, status, error,
                    speaker_name, speaker_confidence, speaker_status,
                    direction_raw_angle_deg, direction_angle_deg, direction_label,
                    direction_confidence, direction_status, direction_spread_deg,
                    direction_speech_samples, direction_total_samples,
                    direction_clusters_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    direction.raw_angle_degrees if direction else None,
                    direction.angle_degrees if direction else None,
                    direction.label if direction else None,
                    direction.confidence if direction else None,
                    direction.status if direction else None,
                    direction.spread_degrees if direction else None,
                    direction.speech_sample_count if direction else None,
                    direction.total_sample_count if direction else None,
                    clusters_json,
                    datetime.now().astimezone().isoformat(),
                ),
            )
            row_id = int(cursor.lastrowid)
            if direction and direction.samples:
                self.connection.executemany(
                    """
                    INSERT INTO direction_samples (
                        segment_id, offset_ms, raw_angle_deg, speech_detected
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        (
                            row_id,
                            sample.offset_ms,
                            sample.raw_angle_degrees,
                            int(sample.speech_detected),
                        )
                        for sample in direction.samples
                    ),
                )
        return row_id

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

    def replace_pending_calendar_candidates(
        self, target_date: date, candidates: list[dict[str, object]]
    ) -> None:
        now = datetime.now().astimezone().isoformat()
        with self.connection:
            self.connection.execute(
                "DELETE FROM calendar_candidates WHERE summary_date = ? AND status = 'pending'",
                (target_date.isoformat(),),
            )
            self.connection.executemany(
                """
                INSERT OR IGNORE INTO calendar_candidates (
                    summary_date, title, starts_at, ends_at, all_day, notes,
                    member_name, suggested_calendar_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                [
                    (
                        target_date.isoformat(),
                        str(candidate["title"]),
                        str(candidate["starts_at"]),
                        str(candidate["ends_at"]),
                        int(bool(candidate["all_day"])),
                        str(candidate.get("notes", "")),
                        str(candidate.get("member_name", "")),
                        str(candidate.get("suggested_calendar_id", "")),
                        now,
                        now,
                    )
                    for candidate in candidates
                ],
            )

    def pending_calendar_candidates(self, limit: int = 50) -> list[CalendarCandidate]:
        rows = self.connection.execute(
            """
            SELECT id, summary_date, title, starts_at, ends_at, all_day, notes,
                   member_name, suggested_calendar_id, status
            FROM calendar_candidates
            WHERE status = 'pending'
            ORDER BY starts_at, id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            CalendarCandidate(
                id=int(row[0]),
                summary_date=str(row[1]),
                title=str(row[2]),
                starts_at=str(row[3]),
                ends_at=str(row[4]),
                all_day=bool(row[5]),
                notes=str(row[6]),
                member_name=str(row[7]),
                suggested_calendar_id=str(row[8]),
                status=str(row[9]),
            )
            for row in rows
        ]

    def mark_calendar_candidate(
        self,
        candidate_id: int,
        status: str,
        *,
        external_event_id: str = "",
        error: str = "",
    ) -> bool:
        if status not in {"created", "dismissed", "failed"}:
            raise ValueError("invalid calendar candidate status")
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE calendar_candidates
                SET status = ?, external_event_id = ?, error = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (
                    status,
                    external_event_id,
                    error,
                    datetime.now().astimezone().isoformat(),
                    candidate_id,
                ),
            )
        return cursor.rowcount == 1

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
