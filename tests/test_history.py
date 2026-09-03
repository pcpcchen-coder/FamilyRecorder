from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

from family_recorder import cli
from family_recorder.config import AppConfig, StorageConfig
from family_recorder.history import HistoryError, build_history, render_markdown
from family_recorder.summary import DailySummaryRunner


def journal(root: Path, kind: str, day: str, text: str) -> Path:
    path = root / kind / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Elements(HTMLParser):
    def __init__(self, source: str):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_empty_history_is_readable_without_database_or_cloud(tmp_path: Path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("History must not start any subprocess, recorder or cloud request")

    monkeypatch.setattr(subprocess, "run", forbidden)
    path = build_history(tmp_path)
    assert path == tmp_path / "history" / "index.html"
    assert "還沒有紀錄" in path.read_text()
    assert not (tmp_path / "listener.sqlite3").exists()
    assert not (tmp_path / "audio").exists()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_all_dates_order_navigation_search_and_source_preservation(tmp_path: Path):
    old = journal(
        tmp_path, "transcripts", "2026-08-30", "### 19:40 — 可能：家人甲 — 方向：左侧\n包裹"
    )
    summary = journal(tmp_path, "summaries", "2026-08-30", "## 事件時間軸\n- 約 19:40：拿包裹")
    current = journal(tmp_path, "transcripts", "2026-09-03", "只有逐字稿")
    journal(tmp_path, "summaries", "2026-09-01", "只有摘要")
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (old, summary, current)
    }
    index = build_history(tmp_path)
    source = index.read_text()
    cards = [attrs for tag, attrs in Elements(source).elements if attrs.get("class") == "day-card"]
    assert [card["data-month"] for card in cards] == ["2026-09", "2026-09", "2026-08"]
    assert "包裹" in cards[2]["data-search"]
    assert cards[0]["data-state"] == "pending"
    assert cards[1]["data-state"] == "ready"
    oldest = (index.parent / "2026-08-30.html").read_text()
    assert 'href="2026-09-01.html"' in oldest
    assert 'href="../transcripts/2026-08-30.md"' in oldest
    assert "19:40 — 可能：家人甲 — 方向：左侧" in oldest
    assert 'data-default="transcript"' in (index.parent / "2026-09-03.html").read_text()
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


def test_marks_transcript_newer_than_summary(tmp_path: Path):
    transcript = journal(tmp_path, "transcripts", "2026-09-03", "新內容")
    summary = journal(tmp_path, "summaries", "2026-09-03", "先前摘要")
    os.utime(summary, (1000, 1000))
    os.utime(transcript, (2000, 2000))
    path = build_history(tmp_path)
    assert 'data-state="stale"' in path.read_text()
    assert "尚未包含於這份摘要" in (path.parent / "2026-09-03.html").read_text()


def test_rebuild_updates_and_prunes_only_owned_pages(tmp_path: Path):
    transcript = journal(tmp_path, "transcripts", "2026-09-03", "舊內容")
    old = journal(tmp_path, "transcripts", "2026-09-02", "待移除內容")
    index = build_history(tmp_path)
    extra = index.parent / "notes.html"
    extra.write_text("user-owned")
    foreign = index.parent / "2020-01-01.html"
    foreign.write_text("user-owned dated page")
    transcript.write_text("新內容")
    old.unlink()
    build_history(tmp_path)
    assert "新內容" in (index.parent / "2026-09-03.html").read_text()
    assert "舊內容" not in (index.parent / "2026-09-03.html").read_text()
    assert not (index.parent / "2026-09-02.html").exists()
    assert extra.read_text() == "user-owned"
    assert foreign.read_text() == "user-owned dated page"


def test_only_canonical_dates_and_regular_source_files(tmp_path: Path):
    for day in ("2026-02-30", "notes", "20260903", "2026-W36-4"):
        journal(tmp_path, "transcripts", day, "must-not-appear")
    secret = tmp_path / "private.txt"
    secret.write_text("unrelated secret")
    (tmp_path / "transcripts" / "2026-09-03.md").symlink_to(secret)
    index = build_history(tmp_path)
    assert "must-not-appear" not in index.read_text()
    assert "unrelated secret" not in index.read_text()
    assert not (index.parent / "2026-09-03.html").exists()


@pytest.mark.parametrize("kind", ["history", "transcripts", "summaries"])
def test_symlinked_directories_are_not_followed(tmp_path: Path, kind: str):
    elsewhere = tmp_path / "unrelated"
    elsewhere.mkdir()
    (tmp_path / kind).symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(HistoryError, match="symlink"):
        build_history(tmp_path)
    assert list(elsewhere.iterdir()) == []


def test_nonempty_unowned_history_directory_is_preserved(tmp_path: Path):
    directory = tmp_path / "history"
    directory.mkdir()
    page = directory / "index.html"
    page.write_text("existing user document")
    with pytest.raises(HistoryError, match="not empty"):
        build_history(tmp_path)
    assert page.read_text() == "existing user document"


def test_unowned_date_page_inside_owned_directory_is_not_overwritten(tmp_path: Path):
    index = build_history(tmp_path)
    page = index.parent / "2026-09-03.html"
    page.write_text("my own HTML")
    journal(tmp_path, "transcripts", "2026-09-03", "recording")
    with pytest.raises(HistoryError, match="unowned HTML"):
        build_history(tmp_path)
    assert page.read_text() == "my own HTML"


def test_failed_atomic_replacement_preserves_existing_index(tmp_path: Path, monkeypatch):
    index = build_history(tmp_path)
    original = index.read_bytes()
    journal(tmp_path, "transcripts", "2026-09-03", "new recording")
    replace = os.replace

    def fail_index(source, target):
        if Path(target) == index:
            raise OSError("simulated disk error")
        return replace(source, target)

    monkeypatch.setattr(os, "replace", fail_index)
    with pytest.raises(OSError, match="disk error"):
        build_history(tmp_path)
    assert index.read_bytes() == original
    assert not list(index.parent.glob(".history-*"))


def test_untrusted_markdown_cannot_execute_or_load_external_resources(tmp_path: Path):
    payload = (
        '<script>alert(1)</script><img src="https://invalid/track" onerror="alert(2)">\n'
        '" autofocus onfocus="alert(3)\n'
        "![tracking](https://invalid/pixel) [click](javascript:alert(4))\n"
        '**<iframe src="file:///etc/passwd">**\n'
        '</script><script>document.body.textContent="bad"</script>'
    )
    journal(tmp_path, "summaries", "2026-09-03", payload)
    index = build_history(tmp_path)
    for path in (index, index.parent / "2026-09-03.html"):
        source = path.read_text()
        assert "&lt;script&gt;" in source
        for tag, attrs in Elements(source).elements:
            assert tag not in {"img", "iframe", "object", "embed", "form"}
            assert not any(key.startswith("on") for key in attrs)
            if tag == "script":
                assert attrs == {}
            for attr in ("href", "src"):
                if attr in attrs:
                    assert not attrs[attr].startswith(("http", "javascript:", "file:", "//"))
        assert "connect-src 'none'" in source


def test_markdown_subset_formats_headings_lists_tables_and_literal_code():
    result = render_markdown(
        "# 標題\n\n**重要** `code`\n\n- 一\n- 二\n\n"
        "| 時間 | 事件 |\n| --- | --- |\n| 19:40 | 包裹 |\n\n"
        "> 提醒\n\n```\n<script>\n```\n\n尾段"
    )
    assert "<h2>標題</h2>" in result
    assert "<strong>重要</strong>" in result
    assert "<ul>\n<li>一</li>\n<li>二</li>\n</ul>" in result
    assert "<table>" in result and "<td>19:40</td>" in result
    assert "<blockquote>提醒</blockquote>" in result
    assert "<pre><code>&lt;script&gt;</code></pre>" in result
    assert "<p>尾段</p>" in result


def test_manual_cli_build_does_not_require_whisper_or_summary_enabled(tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(f"storage:\n  data_dir: {str(tmp_path)!r}\nsummary:\n  enabled: false\n")
    assert cli.main(["--config", str(config), "build-history"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "history" / "index.html")


def test_summary_success_refreshes_history_but_refresh_failure_keeps_summary(tmp_path, monkeypatch):
    journal(tmp_path, "transcripts", "2026-09-03", "### 19:40\n拿包裹")
    calls = []

    def fake(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="## 事件時間軸\n- 約 19:40：拿包裹", stderr="")

    runner = DailySummaryRunner(
        AppConfig(storage=StorageConfig(data_dir=tmp_path)),
        command_runner=fake,
        binary_resolver=lambda _: Path("/fake/codex"),
    )
    summary = runner.run(date(2026, 9, 3))
    assert "拿包裹" in (tmp_path / "history" / "2026-09-03.html").read_text()
    assert len(calls) == 1

    def broken(_):
        raise OSError("disk error")

    monkeypatch.setattr("family_recorder.summary.build_history", broken)
    assert runner.run(date(2026, 9, 3)) == summary
    assert summary.is_file()
    assert len(calls) == 2


def test_concurrent_builds_and_assets_are_complete(tmp_path: Path):
    journal(tmp_path, "transcripts", "2026-09-03", "測試" * 1000)
    with ThreadPoolExecutor(max_workers=3) as pool:
        paths = list(pool.map(build_history, [tmp_path] * 3))
    assert len(set(paths)) == 1
    assert "</html>" in paths[0].read_text()
    for tag in ("script", "style"):
        content = re.search(f"<{tag}>(.*?)</{tag}>", paths[0].read_text(), re.S)[1]
        assert len(content) > 1000
        checksum = base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()
        assert f"'sha256-{checksum}'" in paths[0].read_text()
    assert not list(paths[0].parent.glob(".history-*"))


def test_menu_status_exposes_stable_history_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_listener_is_running", lambda: False)
    config = AppConfig(storage=StorageConfig(data_dir=tmp_path))
    result = cli._menu_status(config, tmp_path / "config.yaml")
    assert result["history_index"] == str(tmp_path / "history" / "index.html")
