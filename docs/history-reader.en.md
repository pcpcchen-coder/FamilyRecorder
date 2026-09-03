# History reader

**English** · [繁體中文](history-reader.md) · [Back to docs index](README.en.md)

## Open the reader

Click the FamilyRecorder menu-bar icon → **閱讀歷史紀錄…** (Read history). The app refreshes the local reading copy, then opens it in your default browser. It does not start recording, regenerate summaries, contact ChatGPT or upload data.

To bookmark the file or find it yourself, choose **打開… → 歷史紀錄首頁的位置** (Open → History homepage location). Finder selects `history/index.html`. Its default location is `~/xvf3800-listener-data/history/index.html`; a custom `storage.data_dir` is respected.

## Reading

- The homepage lists source-summary dates newest first, with separate **200-character brief** and **added calendar events** sections per card. Filter by month, summary status, dates with added events, or search **dates, full summaries and calendar text**.
- “Read the latest day” opens the most recent date with data, not necessarily today.
- A day has **200-character brief / Google Calendar / full summary / full transcript** views and links to older/newer dates. It opens in the brief when available, otherwise the full summary, transcript, or remaining calendar-only records.
- **Find on page** searches the selected view. Enter a name, time or phrase, then press Enter / “Next” to jump through matches. The homepage does not search the entire transcript archive.
- Enlarge text, print the selected view, or save a PDF through the macOS print dialog. The page follows the system light/dark theme.
- Download the source Markdown. Original text, timestamps, speaker and direction hints are not rewritten.

Days without a summary still show their transcript. A **transcript has new content** notice appears when the transcript file was modified after the summary. This is an mtime hint, not a semantic content comparison; manual edits/restores may also trigger it.

### Separate briefs and calendar records

- Briefs are extracted from existing 200-character summary headings, including numbered/bold variants and legacy 100-character sections. Custom prompts are unchanged; there is no new AI request.
- The view shows at most 200 characters. Longer sections are explicitly marked as truncated; the complete source remains in the full-summary view. When no brief is found, the tab says so and the homepage explicitly labels its fallback as a full-summary excerpt, not a newly generated brief.
- The **Google Calendar** tab reads local SQLite records: title, activity start/end dates, timezone, all-day flag, related member and notes. Homepage cards show the added count and first two previews; success is not inferred from summary prose.
- Only `created` records count as added: the app acknowledged a successful system EventKit write. Pending/confirmation, failed and dismissed entries have separate collapsed groups. Failed operations whose status was not changed remain pending.
- Pages are grouped by **source-summary date**, while event cards display the **activity date**, which may be in the future. All-day end dates are exclusive.
- This is a **local write snapshot, not a live Google cloud sync check**. Later calendar edits/deletions are not reflected. Existing records do not store the actual destination calendar name, so suggested IDs are not presented as the actual destination. Related members are not confirmed speaker identities.

## Refresh timing

1. Every successful summary (scheduled, specific date, or “Summarize today”) refreshes the homepage and date pages.
2. Opening the reader or revealing its location from the menu also refreshes it, including today's not-yet-summarized transcript.
3. The app also refreshes after successfully recording an event as created or dismissed. Events automatically created after a summary do not have to wait until tomorrow's summary to appear.
4. An open page is a **snapshot**, not a live listener. Open the menu entry again and reload the browser for current content. Browser reload alone does not rebuild the HTML.

Refresh without another AI call:

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" build-history
```

This prints the homepage path and also works with `summary.enabled: false`. No additional schedule or configuration is required.

## Privacy, files and failures

- Reads only `transcripts/YYYY-MM-DD.md`, `summaries/YYYY-MM-DD.md`, and allowlisted text/status columns of `listener.sqlite3`'s `calendar_candidates`. The connection is read-only and never creates or migrates the database. No WAVs, other tables, voice features, credentials or external event/calendar IDs are read. Rejected recognition results are not imported.
- Missing databases or older databases without the calendar table still work. An unreadable database shows an unavailable notice, not a misleading zero count; summaries/transcripts remain readable.
- `history/` is a rebuildable **sensitive text copy**, not a public website. Directory permissions are `0700`, files `0600`. Do not place it on a public host or in an untrusted sync folder.
- No server, external fonts/images/CDNs, tracking or network requests. HTML, links and image syntax inside content remain inert text. Supported Markdown includes headings, bold, lists, quotes, code and simple tables; other syntax remains literal.
- Only the owned output directory is updated. An existing nonempty unowned `history/` or a symlink produces an error and preserves existing files. Source Markdown is never modified.
- A lock and atomic per-file replacements prevent concurrent writers from truncating files. Reader failure preserves a completed summary, does not repeat cloud/calendar work, and is logged. Retry with `build-history`.
- Audio retention does not delete transcripts, summaries or reader copies. A generated date page is removed on refresh only when **both its Markdown and SQLite calendar sources are gone**. Deleting Markdown alone retains calendar records. Pruning is skipped if the database cannot be read. Already-open tabs/downloaded copies must be closed/removed separately.
- Complete uninstall includes the generated `history/`; keep-data uninstall preserves it. Do not store custom files in this generated directory.

## Acceptance

1. An empty archive shows an empty state; transcript-only dates open directly in transcript view.
2. A successful dated summary appears in the archive; rerunning does not duplicate dates.
3. Month, status and summary-text filters work together; clearing search restores the list.
4. Day views support switching, navigation, multiple search matches, larger text and printing, preserving time/speaker/direction hints.
5. Previously generated pages still open offline, without starting capture or AI.
6. `<script>` and image URLs in test Markdown render only as text, never executing/loading URLs.
7. The brief excludes subsequent calendar sections; a missing brief does not trigger AI. Full summaries remain available.
8. Added counts exclude pending entries; future activity dates and timezones are visible. After event creation, reloading the open page shows the new status without creating another event.

Tests: `pytest tests/test_history.py tests/test_history_data.py tests/test_uninstaller.py`; DOM interactions: `FR_TEST_PYTHON=.venv/bin/python npm test` (first run `npm ci --ignore-scripts`). Fictional fixtures live under `tests/fixtures/history/` and contain no real household conversations.
