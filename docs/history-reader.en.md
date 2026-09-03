# History reader

**English** · [繁體中文](history-reader.md) · [Back to docs index](README.en.md)

## Open the reader

Click the FamilyRecorder menu-bar icon → **閱讀歷史紀錄…** (Read history). The app refreshes the local reading copy, then opens it in your default browser. It does not start recording, regenerate summaries, contact ChatGPT or upload data.

To bookmark the file or find it yourself, choose **打開… → 歷史紀錄首頁的位置** (Open → History homepage location). Finder selects `history/index.html`. Its default location is `~/xvf3800-listener-data/history/index.html`; a custom `storage.data_dir` is respected.

## Reading

- The homepage lists dates newest first. Filter by month, summary status, or search **dates and full summary text**.
- “Read the latest day” opens the most recent date with data, not necessarily today.
- A day has **summary / full transcript** views and links to older/newer recorded dates.
- **Find on page** searches the selected view. Enter a name, time or phrase, then press Enter / “Next” to jump through matches. The homepage does not search the entire transcript archive.
- Enlarge text, print the selected view, or save a PDF through the macOS print dialog. The page follows the system light/dark theme.
- Download the source Markdown. Original text, timestamps, speaker and direction hints are not rewritten.

Days without a summary still show their transcript. A **transcript has new content** notice appears when the transcript file was modified after the summary. This is an mtime hint, not a semantic content comparison; manual edits/restores may also trigger it.

## Refresh timing

1. Every successful summary (scheduled, specific date, or “Summarize today”) refreshes the homepage and date pages.
2. Opening the reader or revealing its location from the menu also refreshes it, including today's not-yet-summarized transcript.
3. An open page is a **snapshot**, not a live listener. Open the menu entry again and reload the browser for current content. Browser reload alone does not rebuild the HTML.

Refresh without another AI call:

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" build-history
```

This prints the homepage path and also works with `summary.enabled: false`. No additional schedule or configuration is required.

## Privacy, files and failures

- Reads only `transcripts/YYYY-MM-DD.md` and `summaries/YYYY-MM-DD.md`, not WAVs, SQLite, voice features or credentials. Rejected recognition results are not imported.
- `history/` is a rebuildable **sensitive text copy**, not a public website. Directory permissions are `0700`, files `0600`. Do not place it on a public host or in an untrusted sync folder.
- No server, external fonts/images/CDNs, tracking or network requests. HTML, links and image syntax inside content remain inert text. Supported Markdown includes headings, bold, lists, quotes, code and simple tables; other syntax remains literal.
- Only the owned output directory is updated. An existing nonempty unowned `history/` or a symlink produces an error and preserves existing files. Source Markdown is never modified.
- A lock and atomic per-file replacements prevent concurrent writers from truncating files. Reader failure preserves a completed summary, does not repeat cloud/calendar work, and is logged. Retry with `build-history`.
- Audio retention does not delete transcripts, summaries or reader copies. After source Markdown is manually removed, the next refresh removes corresponding generated date pages. Already-open tabs and downloaded copies must be closed/removed separately.
- Complete uninstall includes the generated `history/`; keep-data uninstall preserves it. Do not store custom files in this generated directory.

## Acceptance

1. An empty archive shows an empty state; transcript-only dates open directly in transcript view.
2. A successful dated summary appears in the archive; rerunning does not duplicate dates.
3. Month, status and summary-text filters work together; clearing search restores the list.
4. Day views support switching, navigation, multiple search matches, larger text and printing, preserving time/speaker/direction hints.
5. Previously generated pages still open offline, without starting capture or AI.
6. `<script>` and image URLs in test Markdown render only as text, never executing/loading URLs.

Tests: `pytest tests/test_history.py tests/test_uninstaller.py`. Fictional reading fixtures live under `tests/fixtures/history/` and contain no real household conversations.
