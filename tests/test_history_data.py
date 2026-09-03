from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from family_recorder import cli
from family_recorder.config import StorageConfig
from family_recorder.history import build_history
from family_recorder.history_data import extract_brief, read_calendar_snapshot
from family_recorder.storage import Storage


@pytest.mark.parametrize(
    "heading",
    [
        "## 7. 今日摘要（200 字內）",
        "## 200 字內今日摘要",
        "## **200字摘要**",
        "**今日摘要（200 字內）**",
        "## 9. 200 字摘要 ##",
    ],
)
def test_brief_variants_stop_before_calendar_section(heading):
    brief = extract_brief(
        f"## 其他\n不是短摘要\n{heading}\n\n真正的短摘要。\n\n## Google Calendar 事件\n不要混入"
    )
    assert brief.text == "真正的短摘要。"
    assert brief.source_label == "原文 200 字摘要"
    assert not brief.truncated


def test_brief_missing_legacy_length_and_fenced_examples():
    assert not extract_brief("## 每日摘要\n不能假冒短摘要").text
    assert not extract_brief("```\n## 200 字摘要\n不是摘要\n```").text
    assert not extract_brief("## 200 字摘要\n\n## 下一段\n不是摘要").text
    legacy = extract_brief("## 100 字內摘要\n舊的短摘要")
    assert legacy.source_label == "原文 100 字摘要"
    assert legacy.text == "舊的短摘要"
    source = "## 100 字摘要\n舊版\n## 200 字摘要\n" + "字" * 201
    assert extract_brief(source).text == "字" * 200
    assert extract_brief(source).truncated


def seed_calendar(root: Path) -> list[int]:
    with Storage(StorageConfig(data_dir=root)) as storage:
        storage.replace_pending_calendar_candidates(
            date(2026, 9, 2),
            [
                {
                    "title": title,
                    "starts_at": "2026-10-01T09:00:00+08:00",
                    "ends_at": "2026-10-01T10:00:00+08:00",
                    "all_day": index == 1,
                    "notes": '原文備註 <img src=x onerror="alert(1)">',
                    "member_name": "家人甲",
                    "suggested_calendar_id": "private-calendar-id",
                }
                for index, title in enumerate(["牙齒檢查", "郊遊", "失敗測試", "略過測試"])
            ],
        )
        ids = [event.id for event in storage.pending_calendar_candidates()]
        storage.mark_calendar_candidate(ids[0], "created", external_event_id="private-event-id")
        storage.mark_calendar_candidate(ids[2], "failed", error="private-error")
        storage.mark_calendar_candidate(ids[3], "dismissed")
    return ids


def test_calendar_snapshot_readonly_and_allowlisted(tmp_path, monkeypatch):
    seed_calendar(tmp_path)
    path = tmp_path / "listener.sqlite3"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    connect = sqlite3.connect
    statements = []

    def readonly(database, **kwargs):
        assert database.endswith("?mode=ro") and kwargs["uri"]
        connection = connect(database, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr("family_recorder.history_data.sqlite3.connect", readonly)
    snapshot = read_calendar_snapshot(tmp_path)
    assert not snapshot.unavailable
    assert len(snapshot.events) == 4
    assert {event.status for event in snapshot.events} == {
        "created",
        "pending",
        "failed",
        "dismissed",
    }
    assert all(
        not any(key in query for key in ("external_event_id", "suggested_calendar_id", "segments"))
        for query in statements
    )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_calendar_panels_status_search_future_dates_and_no_private_ids(tmp_path):
    seed_calendar(tmp_path)
    index = build_history(tmp_path)
    # A calendar-only source date remains readable, even without Markdown.
    page = (index.parent / "2026-09-02.html").read_text()
    assert not (index.parent / "2026-10-01.html").exists()
    assert 'data-default="calendar"' in page
    assert 'data-calendar="1"' in index.read_text()
    assert "已加入行事曆 · 1 筆" in page
    assert "尚待建立／確認 · 1 筆" in page
    assert "建立失敗 · 1 筆" in page
    assert "已略過 · 1 筆" in page
    assert "2026-10-01 09:00 UTC+08:00" in page
    assert "全天 · 2026-10-01 → 2026-10-01（結束日不含）" in page
    assert "家人甲" in page and "&lt;img" in page
    for text in (page, index.read_text()):
        assert "private-calendar-id" not in text
        assert "private-event-id" not in text
        assert "private-error" not in text
        assert "<img" not in text
    assert "牙齒檢查" in index.read_text()
    assert "尚無獨立的 200 字摘要" in page


@pytest.mark.parametrize("count", [3, 5])
def test_homepage_lists_every_created_event_without_truncation(tmp_path, count):
    with Storage(StorageConfig(data_dir=tmp_path)) as storage:
        storage.replace_pending_calendar_candidates(
            date(2026, 9, 2),
            [
                {
                    "title": f"完整事件 {index}",
                    "starts_at": "2026-10-01T09:00:00+08:00",
                    "ends_at": "2026-10-01T10:00:00+08:00",
                    "all_day": False,
                }
                for index in range(count + 1)
            ],
        )
        for candidate in storage.pending_calendar_candidates()[:count]:
            storage.mark_calendar_candidate(candidate.id, "created")
    source = build_history(tmp_path).read_text()
    events = re.search(r'<ul class="calendar-preview">(.*?)</ul>', source, re.S)[1]
    assert events.count("<li>") == count
    assert events.count("2026-10-01 09:00 UTC+08:00") == count
    for index in range(count):
        assert f"完整事件 {index}" in events
    assert f"完整事件 {count}" not in events  # the pending event is still excluded
    assert f'data-calendar="{count}"' in source


@pytest.mark.parametrize("case", ["absent", "old", "corrupt", "symlink", "columns"])
def test_calendar_database_failures_do_not_break_journal(tmp_path, case):
    path = tmp_path / "listener.sqlite3"
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "transcripts" / "2026-09-03.md").write_text("可以閱讀逐字稿")
    if case == "old":
        sqlite3.connect(path).close()
    elif case == "corrupt":
        path.write_text("not a database")
    elif case == "symlink":
        secret = tmp_path / "unrelated.db"
        secret.write_text("do not read")
        path.symlink_to(secret)
    elif case == "columns":
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE calendar_candidates (id INTEGER)")
    index = build_history(tmp_path)
    page = (index.parent / "2026-09-03.html").read_text()
    assert "可以閱讀逐字稿" in page
    assert ("暫時無法讀取" in page) == (case in {"corrupt", "symlink", "columns"})
    if case == "absent":
        assert not path.exists()


def test_invalid_source_dates_and_event_times_are_safe(tmp_path):
    seed_calendar(tmp_path)
    with sqlite3.connect(tmp_path / "listener.sqlite3") as db:
        db.execute(
            "UPDATE calendar_candidates SET summary_date='../../escape' WHERE status='failed'"
        )
        db.execute(
            "UPDATE calendar_candidates SET summary_date='2026-W36-3' WHERE status='dismissed'"
        )
        db.execute("UPDATE calendar_candidates SET starts_at='<script>' WHERE status='created'")
    assert len(read_calendar_snapshot(tmp_path).events) == 2
    index = build_history(tmp_path)
    page = (index.parent / "2026-09-02.html").read_text()
    assert "時間格式待確認：&lt;script&gt;" in page


def test_summary_prose_cannot_mark_an_event_as_created(tmp_path):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    source = "## 200 字摘要\n一段短摘要。\n\n## Google Calendar\n已加入三個事件。"
    (summaries / "2026-09-02.md").write_text(source)
    index = build_history(tmp_path)
    page = (index.parent / "2026-09-02.html").read_text()
    assert 'data-calendar="0"' in index.read_text()
    assert "已加入行事曆 · 0 筆" in page
    assert "已加入三個事件。" in page  # original full summary still intact
    assert 'data-default="brief"' in page
    assert (summaries / "2026-09-02.md").read_text() == source


def test_locked_database_does_not_prune_calendar_only_pages(tmp_path, monkeypatch):
    seed_calendar(tmp_path)
    index = build_history(tmp_path)
    page = index.parent / "2026-09-02.html"
    before = page.read_bytes()

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("family_recorder.history_data.sqlite3.connect", locked)
    build_history(tmp_path)
    assert "暫時無法讀取" in index.read_text()
    assert page.read_bytes() == before


@pytest.mark.parametrize("command", ["calendar-event-created", "dismiss-calendar-event"])
def test_calendar_cli_refreshes_after_commit_and_failure_does_not_retry(
    tmp_path, monkeypatch, command
):
    ids = seed_calendar(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text(f"storage:\n  data_dir: {str(tmp_path)!r}\n")
    args = ["--config", str(config), command, "--id", str(ids[1])]
    assert cli.main(args) == 0
    page = (tmp_path / "history" / "2026-09-02.html").read_text()
    assert "尚待建立／確認 · 1 筆" not in page
    assert (
        "已加入行事曆 · 2 筆" if command == "calendar-event-created" else "已略過 · 2 筆"
    ) in page
    with sqlite3.connect(tmp_path / "listener.sqlite3") as db:
        db.execute("UPDATE calendar_candidates SET status='pending' WHERE id=?", (ids[1],))
    calls = []

    def fail(_):
        calls.append(True)
        raise OSError("disk error")

    monkeypatch.setattr(cli, "build_history", fail)
    assert cli.main(args) == 0
    assert calls == [True]
    assert cli.main(args) == 1  # already committed, not retried as another calendar write
    assert calls == [True]
