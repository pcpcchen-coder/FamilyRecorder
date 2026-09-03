"""Build an offline, disposable reading view from the existing Markdown journals.

This module has no audio, network or summary-client access. Inputs are canonical
date-named Markdown and a read-only calendar text snapshot; HTML is always text.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import html
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import date, datetime
from functools import cache
from importlib.resources import files
from pathlib import Path

from family_recorder.history_data import HistoryCalendarEvent, extract_brief, read_calendar_snapshot

MARKER = "FamilyRecorder offline history v1\n"
PAGE_MARKER = "<!-- FamilyRecorder generated history v1 -->\n"
DATE_NAME = re.compile(r"\d{4}-\d{2}-\d{2}")


class HistoryError(RuntimeError):
    """The reading view could not be safely updated."""


def history_index_path(data_dir: Path) -> Path:
    return data_dir / "history" / "index.html"


def _inline(text: str) -> str:
    # Escape first. Never render links, images or user-supplied HTML attributes.
    escaped = html.escape(text)
    return re.sub(
        r"`([^`\n]+)`|\*\*([^*\n]+)\*\*",
        lambda m: f"<code>{m[1]}</code>" if m[1] is not None else f"<strong>{m[2]}</strong>",
        escaped,
    )


def render_markdown(text: str) -> str:
    """A small, non-executable Markdown subset, with a readable literal fallback."""
    output: list[str] = []
    paragraph: list[str] = []
    code: list[str] | None = None
    fence = ""
    list_tag = ""
    lines = text.splitlines()

    def flush() -> None:
        nonlocal list_tag
        if paragraph:
            output.append("<p>" + "<br>".join(_inline(line) for line in paragraph) + "</p>")
            paragraph.clear()
        if list_tag:
            output.append(f"</{list_tag}>")
            list_tag = ""

    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if code is not None:
            if line.startswith(fence):
                output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = None
            else:
                code.append(line)
            continue
        if line.startswith(("```", "~~~")):
            flush()
            fence = line[:3]
            code = []
        elif not line.strip():
            flush()
        elif re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", line):
            flush()
            output.append("<hr>")
        elif heading := re.match(r"^(#{1,6})\s+(.*)", line):
            flush()
            level = max(2, len(heading[1]))
            output.append(f"<h{level}>{_inline(heading[2])}</h{level}>")
        elif (
            "|" in line
            and index < len(lines)
            and re.fullmatch(r"\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*", lines[index])
        ):
            flush()
            headers = line.strip().strip("|").split("|")
            output.append('<div class="table-wrap"><table><thead><tr>')
            output.extend(f"<th>{_inline(cell.strip())}</th>" for cell in headers)
            output.append("</tr></thead><tbody>")
            index += 1
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = lines[index].strip().strip("|").split("|")
                output.append("<tr>" + "".join(f"<td>{_inline(c.strip())}</td>" for c in cells))
                output.append("</tr>")
                index += 1
            output.append("</tbody></table></div>")
        elif entry := re.match(r"^\s*(?:[-*+] |\d+[.)] )(.*)", line):
            tag = "ol" if re.match(r"\s*\d", line) else "ul"
            if paragraph or list_tag != tag:
                flush()
                output.append(f"<{tag}>")
                list_tag = tag
            output.append(f"<li>{_inline(entry[1])}</li>")
        elif line.startswith("> "):
            flush()
            output.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        else:
            if list_tag:
                flush()
            paragraph.append(line)
    flush()
    if code is not None:
        output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    return "\n".join(output)


@cache
def _assets() -> tuple[str, str, str, str]:
    directory = files("family_recorder").joinpath("history_assets")
    css = directory.joinpath("reader.css").read_text(encoding="utf-8")
    script = directory.joinpath("reader.js").read_text(encoding="utf-8")
    hashes = [
        base64.b64encode(hashlib.sha256(text.encode()).digest()).decode() for text in (css, script)
    ]
    return css, script, hashes[0], hashes[1]


def _document(title: str, body: str) -> str:
    # Hash-authorized, bundled inline assets work without file:// origin/CORS
    # assumptions and without unsafe-inline or any external resource loads.
    css, script, css_hash, script_hash = _assets()
    return (
        PAGE_MARKER
        + f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';
 style-src 'sha256-{css_hash}'; script-src 'sha256-{script_hash}';
 connect-src 'none'; img-src 'none';
 font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{html.escape(title)} · FamilyRecorder</title>
<style>{css}</style>
</head>
<body><div class="shell">
<header class="brand"><a href="index.html">◉ FamilyRecorder</a>
<span class="privacy">僅限本機 · 離線閱讀</span></header>
{body}
<footer>這是本機文字與行事曆寫入紀錄的閱讀副本，不會上傳資料或讀取音訊。<br>
需更新內容時，請再次點選選單列「閱讀歷史紀錄…」，再重新整理瀏覽器。
人別與方向是近似線索，請以原始內容與實際情況為準。</footer>
</div><script>{script}</script></body></html>
"""
    )


def _sources(data_dir: Path, kind: str) -> dict[str, Path]:
    directory = data_dir / kind
    if directory.is_symlink():
        raise HistoryError(f"Refusing a symlinked journal directory: {directory}")
    found: dict[str, Path] = {}
    for path in directory.glob("*.md"):
        if path.is_symlink() or not path.is_file() or not DATE_NAME.fullmatch(path.stem):
            continue
        try:
            date.fromisoformat(path.stem)
        except ValueError:
            continue
        found[path.stem] = path
    return found


def _atomic_write(path: Path, content: str) -> None:
    if path.is_symlink():
        raise HistoryError(f"Refusing a symlinked history file: {path}")
    if path.is_file() and path.suffix == ".html":
        with path.open(encoding="utf-8") as existing:
            if existing.readline() != PAGE_MARKER:
                raise HistoryError(f"Refusing to replace an unowned HTML file: {path}")
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        path.chmod(0o600)
        return
    fd, name = tempfile.mkstemp(prefix=".history-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _locked_directory(data_dir: Path):
    directory = data_dir / "history"
    if directory.is_symlink():
        raise HistoryError(f"Refusing a symlinked history directory: {directory}")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A persistent lock serializes manual refreshes and scheduled summaries.
    lock_path = directory / ".build.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        marker = directory / ".familyrecorder-history"
        if marker.is_symlink():
            raise HistoryError("History ownership marker must not be a symlink")
        if marker.exists():
            if marker.read_text(encoding="utf-8") != MARKER:
                raise HistoryError("Unrecognized history directory; existing files were preserved")
        elif any(path != lock_path for path in directory.iterdir()):
            raise HistoryError("History directory is not empty; existing files were preserved")
        else:
            _atomic_write(marker, MARKER)
        directory.chmod(0o700)
        yield directory


def _preview(text: str) -> str:
    lines = [line.strip(" #*-\t") for line in text.splitlines()]
    readable = " · ".join(
        line for line in lines if line and "FamilyRecorder daily summary" not in line
    )
    return readable[:160] + ("…" if len(readable) > 160 else "")


def _event_time(event: HistoryCalendarEvent) -> str:
    try:
        start = datetime.fromisoformat(event.starts_at)
        end = datetime.fromisoformat(event.ends_at)
    except ValueError:
        return f"時間格式待確認：{event.starts_at} → {event.ends_at}"
    if event.all_day:
        return f"全天 · {start:%Y-%m-%d} → {end:%Y-%m-%d}（結束日不含）"

    def display(value: datetime) -> str:
        offset = value.strftime("%z")
        zone = f"UTC{offset[:3]}:{offset[3:]}" if offset else "時區未記錄"
        return f"{value:%Y-%m-%d %H:%M} {zone}"

    return f"{display(start)} → {display(end)}"


def _calendar_panel(events: list[HistoryCalendarEvent], unavailable: bool) -> str:
    note = (
        '<p class="hint">依摘要來源日期歸檔；下列「活動時間」可能是未來日期。'
        "「已加入」表示 App 已收到系統行事曆寫入成功回覆，不代表 Google 雲端同步已完成。"
        "這不是即時查詢；日曆中後續修改或刪除，請到 Google Calendar 確認。"
        "既有紀錄未保存實際日曆名稱，此處不以建議日曆冒充實際目的地。</p>"
    )
    if unavailable:
        return (
            note
            + '<p class="notice">行事曆紀錄暫時無法讀取，並非沒有事件。請稍後重新開啟閱讀頁。</p>'
        )
    result = [note]
    for status, label in (
        ("created", "已加入行事曆"),
        ("pending", "尚待建立／確認"),
        ("failed", "建立失敗"),
        ("dismissed", "已略過"),
    ):
        selected = [event for event in events if event.status == status]
        if status != "created" and not selected:
            continue
        content = f"<h3>{label} · {len(selected)} 筆</h3>"
        for event in selected:
            member = html.escape(event.member_name or "未指定")
            content += f'''<article class="calendar-event" data-status="{status}">
<h4>{html.escape(event.title)}</h4>
<p class="event-time">活動時間：{html.escape(_event_time(event))}</p>
<p class="event-member">相關成員：{member}（非說話者身分確認）</p>
<p class="event-notes">{html.escape(event.notes or "無備註")}</p></article>'''
        if not selected:
            content += (
                '<p class="empty">這一天沒有已成功寫入的事件紀錄；摘要提到的行程不會自動算入。</p>'
            )
        if status != "created":
            content = (
                f'<details class="calendar-other"><summary>{label} · {len(selected)} 筆</summary>'
                f"{content}</details>"
            )
        result.append(content)
    return "".join(result)


def build_history(data_dir: Path) -> Path:
    """Regenerate the owned view, leaving source Markdown/SQLite untouched."""
    with _locked_directory(data_dir) as directory:
        transcripts = _sources(data_dir, "transcripts")
        summaries = _sources(data_dir, "summaries")
        calendar = read_calendar_snapshot(data_dir)
        calendar_days: dict[str, list[HistoryCalendarEvent]] = {}
        for event in calendar.events:
            calendar_days.setdefault(event.summary_date, []).append(event)
        days = sorted(transcripts.keys() | summaries.keys() | calendar_days.keys(), reverse=True)
        cards: list[str] = []
        months = sorted({day[:7] for day in days}, reverse=True)
        summary_count = 0
        for index, day in enumerate(days):
            transcript = transcripts[day].read_text(encoding="utf-8") if day in transcripts else ""
            summary = summaries[day].read_text(encoding="utf-8") if day in summaries else ""
            has_summary = bool(summary.strip())
            has_transcript = bool(transcript.strip())
            brief = extract_brief(summary)
            events = calendar_days.get(day, [])
            created = [event for event in events if event.status == "created"]
            default_panel = (
                "brief"
                if brief.text
                else "summary"
                if has_summary
                else "transcript"
                if has_transcript
                else "calendar"
            )
            summary_count += has_summary
            stale = (
                has_summary
                and has_transcript
                and transcripts[day].stat().st_mtime_ns > summaries[day].stat().st_mtime_ns
            )
            label = "逐字稿有新內容" if stale else ("已有摘要" if has_summary else "尚無摘要")
            weekday = "一二三四五六日"[date.fromisoformat(day).weekday()]
            preview = brief.text or (_preview(summary) if has_summary else "尚未產生摘要。")
            preview_label = (
                brief.source_label
                if brief.text
                else "完整摘要節錄"
                if has_summary
                else "200 字摘要"
            )
            calendar_text = " ".join(
                f"{event.title} {event.starts_at} {event.ends_at} {event.member_name} {event.notes}"
                for event in events
            )
            search = html.escape(f"{day} {summary} {calendar_text}".lower(), quote=True)
            calendar_label = (
                "行事曆狀態暫時無法讀取"
                if calendar.unavailable
                else f"已加入行事曆 · {len(created)} 筆"
            )
            calendar_preview = "".join(
                f"<li>{html.escape(event.title)}<small>{html.escape(_event_time(event))}</small></li>"
                for event in created
            )
            calendar_preview = (
                f'<ul class="calendar-preview">{calendar_preview}</ul>' if calendar_preview else ""
            )
            state = "stale" if stale else ("ready" if has_summary else "pending")
            cards.append(f"""<article class="day-card" data-month="{day[:7]}"
 data-state="{state}" data-calendar="{len(created)}" data-search="{search}">
<div><a class="date-link" href="{day}.html">{day} <span>週{weekday}</span></a>
<div class="card-brief"><h2>{preview_label}</h2>
<p class="preview">{html.escape(preview)}{"…" if brief.truncated else ""}</p></div>
<div class="card-calendar"><a href="{day}.html#calendar">{calendar_label} →</a>
{calendar_preview}</div></div>
<div class="card-actions"><span class="badge {state}">{label}</span>
<a href="{day}.html#{default_panel}">閱讀 →</a>
<a href="{day}.html#brief">200 字摘要</a></div>
</article>""")
            previous = (
                f'<a href="{days[index + 1]}.html">← 較早一天</a>' if index + 1 < len(days) else ""
            )
            following = f'<a href="{days[index - 1]}.html">較新一天 →</a>' if index > 0 else ""
            source_links = " · ".join(
                f'<a href="../{kind}/{day}.md" download>下載{label_text} Markdown</a>'
                for kind, label_text, available in (
                    ("summaries", "摘要", day in summaries),
                    ("transcripts", "逐字稿", day in transcripts),
                )
                if available
            )
            updated = [
                path[day].stat().st_mtime for path in (transcripts, summaries) if day in path
            ]
            snapshot = (
                datetime.fromtimestamp(max(updated)).strftime("%Y-%m-%d %H:%M")
                if updated
                else "僅有行事曆寫入紀錄"
            )
            notice = (
                '<p class="notice">逐字稿有新內容，尚未包含於這份摘要；請切換逐字稿閱讀，'
                "或從選單列重新執行摘要。</p>"
                if stale
                else ""
            )
            summary_html = (
                render_markdown(summary)
                if has_summary
                else ('<p class="empty">這一天尚無摘要。你仍可切換到逐字稿閱讀。</p>')
            )
            transcript_html = (
                render_markdown(transcript)
                if has_transcript
                else ('<p class="empty">這一天沒有逐字稿內容。</p>')
            )
            brief_html = (
                f'<p class="brief-text">{html.escape(brief.text)}</p>'
                f'<p class="hint">{brief.source_label} · {len(brief.text)} 字元'
                + (
                    " · 原文超過 200 字，這裡只呈現前 200 字；請切換完整摘要。"
                    if brief.truncated
                    else ""
                )
                + "</p>"
                if brief.text
                else (
                    '<p class="empty">尚無獨立的 200 字摘要。請切換完整摘要或逐字稿閱讀；'
                    "不會自動呼叫 AI 補寫。</p>"
                )
            )
            calendar_count = str(len(created)) if not calendar.unavailable else "?"
            body = f"""<nav class="day-nav"><a href="index.html">← 全部日期</a>
<div>{previous} {following}</div></nav>
<h1>{day} <span class="weekday">週{weekday}</span></h1>
<p class="subtitle">文字來源最後修改：{snapshot} · 原有時間、人別與方向標記完整保留</p>
{notice}
<div class="reader-tools" data-default="{default_panel}">
<div class="tabs" role="group" aria-label="閱讀內容">
<button type="button" data-panel="brief">200 字摘要</button>
<button type="button" data-panel="calendar">Google Calendar · {calendar_count}</button>
<button type="button" data-panel="summary">完整摘要</button>
<button type="button" data-panel="transcript">完整逐字稿</button></div>
<div class="text-tools"><button type="button" id="font-size">放大字體</button>
<button type="button" id="print">列印／存成 PDF</button></div>
<div class="find-bar"><label for="find">頁內尋找</label>
<input id="find" type="search" placeholder="姓名、事件或時間，例如 19:40">
<button type="button" id="next-match">下一筆</button>
<span id="match-count" role="status" aria-live="polite"></span></div>
</div>
<noscript><p class="notice">JavaScript 未啟用，
以下依序顯示短摘要、行事曆、完整摘要與逐字稿。</p></noscript>
<main class="reader">
<section id="brief" class="reading-panel" aria-label="200 字摘要">
<h2 class="section-label">200 字摘要</h2>{brief_html}</section>
<section id="calendar" class="reading-panel" aria-label="Google Calendar">
<h2 class="section-label">Google Calendar · 本機寫入紀錄</h2>
{_calendar_panel(events, calendar.unavailable)}</section>
<section id="summary" class="reading-panel" aria-label="完整摘要">
<h2 class="section-label">完整摘要</h2>{summary_html}</section>
<section id="transcript" class="reading-panel" aria-label="完整逐字稿">
<h2 class="section-label">完整逐字稿</h2>{transcript_html}</section>
</main><p class="source-links">{source_links}</p>"""
            _atomic_write(directory / f"{day}.html", _document(day, body))
        options = "".join(f'<option value="{month}">{month}</option>' for month in months)
        latest = f'<a class="primary" href="{days[0]}.html">閱讀最新一天 →</a>' if days else ""
        generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        empty_message = (
            "找不到符合條件的紀錄，請調整搜尋或篩選。"
            if days
            else "還沒有紀錄。完成錄音後，再從選單列開啟此頁即可。"
        )
        calendar_warning = (
            '<p class="notice">行事曆紀錄暫時無法讀取，已加入事件篩選暫不可用。</p>'
            if calendar.unavailable
            else ""
        )
        body = f"""<div class="hero"><div><p class="eyebrow">YOUR FAMILY JOURNAL</p>
<h1>把日常，慢慢讀回來。</h1>
<p class="subtitle">先讀 200 字重點，再看已加入的行程；完整紀錄仍在。</p>
</div>{latest}</div>
<div class="stats"><span><strong>{len(days)}</strong> 天紀錄</span>
<span><strong>{summary_count}</strong> 份摘要</span><span>更新於 {generated}</span></div>
<section class="filters" aria-label="篩選紀錄">
<label>搜尋日期／摘要／行事曆<input id="search" type="search"
 placeholder="例如 2026-09、包裹、家人姓名"></label>
<label>月份<select id="month"><option value="">全部月份</option>{options}</select></label>
<label>摘要狀態<select id="state"><option value="">全部紀錄</option>
<option value="ready">已有摘要</option><option value="pending">尚無摘要</option>
<option value="stale">逐字稿有新內容</option></select></label>
</section><label class="calendar-filter">
<input id="calendar-only" type="checkbox" {"disabled" if calendar.unavailable else ""}>
只看有已加入行事曆事件的日期</label>
<p class="hint">日期依摘要來源日排列，不是行程發生日。
搜尋涵蓋摘要全文與行事曆紀錄；逐字稿請點入當天尋找。</p>
{calendar_warning}
<p id="result-count" role="status" aria-live="polite">共 {len(days)} 天</p>
<main class="day-list">{"".join(cards)}</main>
<p id="no-results" class="empty" {"hidden" if days else ""}>
{empty_message}
</p>"""
        _atomic_write(directory / "index.html", _document("歷史紀錄", body))
        # Delete only our generated date pages whose sources were removed. Never
        # remove source files or unrelated files a user placed in this directory.
        for path in () if calendar.unavailable else directory.glob("*.html"):
            if not DATE_NAME.fullmatch(path.stem) or path.stem in days or path.is_symlink():
                continue
            with path.open(encoding="utf-8") as handle:
                if handle.readline() != PAGE_MARKER:
                    continue
            path.unlink()
    return history_index_path(data_dir)
