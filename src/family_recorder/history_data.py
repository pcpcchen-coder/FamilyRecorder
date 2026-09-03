"""Read-only, text-only inputs for the offline history reader."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Brief:
    text: str
    source_label: str
    truncated: bool = False


def extract_brief(markdown: str) -> Brief:
    """Extract an existing 200/100-character section, never invent a new summary.

    Prefer 200-character headings; numbered and bold headings are supported.
    Ignore fenced examples and stop at the next equal/higher-level heading.
    """
    sections: list[tuple[str, str]] = []
    title = ""
    level = 0
    lines: list[str] = []
    fence = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            if not fence:
                fence = stripped[:3]
            elif stripped.startswith(fence):
                fence = ""
            continue
        if fence:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)", line)
        # Some customized prompts use a standalone bold section title.
        bold = re.fullmatch(r"\*\*(.+)\*\*", stripped)
        if heading or bold:
            next_level = len(heading[1]) if heading else 2
            if title and next_level <= level:
                sections.append((title, "\n".join(lines)))
                title, lines = "", []
            name = heading[2] if heading else bold[1]
            if not title and re.search(r"[12]00\s*字", name) and "摘要" in name:
                title, level = name, next_level
                continue
        if title:
            lines.append(line)
    if title:
        sections.append((title, "\n".join(lines)))
    for size in (200, 100):
        for name, content in sections:
            if not re.search(rf"{size}\s*字", name):
                continue
            plain = " ".join(
                line.strip(" #*`>-\t") for line in content.splitlines() if line.strip()
            ).strip()
            if plain:
                return Brief(plain[:200], f"原文 {size} 字摘要", len(plain) > 200)
    return Brief("", "未找到獨立短摘要")


@dataclass(frozen=True)
class HistoryCalendarEvent:
    summary_date: str
    title: str
    starts_at: str
    ends_at: str
    all_day: bool
    notes: str
    member_name: str
    status: str


@dataclass(frozen=True)
class CalendarSnapshot:
    events: tuple[HistoryCalendarEvent, ...] = ()
    unavailable: bool = False


def read_calendar_snapshot(data_dir: Path) -> CalendarSnapshot:
    """Read only the calendar text allowlist, without creating/migrating a DB.

    `created` is the app's successful EventKit write acknowledgment, not proof
    of current Google server state. IDs, errors, audio and features stay out.
    """
    path = data_dir / "listener.sqlite3"
    if path.is_symlink():
        return CalendarSnapshot(unavailable=True)
    if not path.exists():
        return CalendarSnapshot()
    try:
        with closing(
            sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True, timeout=1)
        ) as db:
            db.execute("PRAGMA query_only = ON")
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_candidates'"
            ).fetchone():
                return CalendarSnapshot()
            rows = db.execute(
                """SELECT summary_date, title, starts_at, ends_at, all_day,
                          notes, member_name, status
                   FROM calendar_candidates
                   WHERE status IN ('created', 'pending', 'failed', 'dismissed')
                   ORDER BY starts_at, id"""
            ).fetchall()
        events: list[HistoryCalendarEvent] = []
        for row in rows:
            day = str(row[0])
            try:
                if date.fromisoformat(day).isoformat() != day:
                    continue
            except ValueError:
                continue
            events.append(
                HistoryCalendarEvent(
                    summary_date=day,
                    title=str(row[1] or "未命名事件"),
                    starts_at=str(row[2] or ""),
                    ends_at=str(row[3] or ""),
                    all_day=bool(row[4]),
                    notes=str(row[5] or ""),
                    member_name=str(row[6] or ""),
                    status=str(row[7]),
                )
            )
        return CalendarSnapshot(tuple(events))
    except (sqlite3.Error, OSError):
        # Do not claim zero events when the database is locked/corrupt/old.
        return CalendarSnapshot(unavailable=True)
