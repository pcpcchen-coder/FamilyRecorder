# Changelog / 變更記錄

All notable changes to FamilyRecorder.
FamilyRecorder 的重要變更記錄。

> ℹ️ **Note / 說明**
> This changelog was reconstructed retroactively from commit history and from the version numbers referenced in the project documentation. Entries whose version number was never recorded are grouped under *Earlier releases* without invented version numbers.
> 這份變更記錄是依據 commit 歷史與文件中提及的版本號回溯整理。文件未記載版本號的項目統一列在「更早的版本」，不虛構版本編號。

Format loosely follows [Keep a Changelog](https://keepachangelog.com/). Versions follow the `version` field in [`pyproject.toml`](pyproject.toml).

---

## [Unreleased]

### Added
- MIT `LICENSE` — the repository previously had no license, which legally prevented reuse and redistribution.
- Bilingual documentation set under `docs/`, with a Traditional Chinese page (`name.md`) and an English page (`name.en.md`) for every topic: getting started, hardware, configuration, daily summary, speakers, menu bar, data model, CLI, privacy, architecture, use cases, roadmap, troubleshooting, development.
- New Mermaid architecture diagrams: layered overview, module dependency map, capture gate decision order, text-filter decision order, per-segment enrichment sequence, cloud summary sequence, calendar candidate state machine, process topology, menu-bar control sequence, uninstall boundary, and trust boundary.
- `docs/use-cases.md` documenting the tutoring / study-review and dream-journal scenarios with prompt templates, plus an explicit split between what works today and what is planned.
- `docs/roadmap.md` describing candidate directions and what is deliberately excluded.
- `CONTRIBUTING`, `SECURITY`, and this changelog, plus GitHub issue and pull request templates.

### Changed
- `README.md` restructured from a single 653-line reference page into a promotion-oriented entry page, with `README.en.md` as its English counterpart. All previous content was relocated into the `docs/` topic pages rather than removed.

---

## [0.14.4]

### Fixed
- Restore macOS calendar authorization. The 0.14.3 Hardened Runtime signature was missing the Calendar entitlement, so macOS rejected the request before the authorization dialog could appear. The menu now shows a configured-but-unauthorized state as needing re-authorization. Existing Google accounts, events, and calendar mappings are preserved.

## [0.14.3]

### Changed
- Stabilize macOS microphone identity. The main app installs to the standard `/Applications/FamilyRecorder.app` and carries the Audio Input entitlement required by Hardened Runtime. Duplicate older apps under Application Support or `~/Applications` are removed automatically. Models, transcripts, and recordings are not moved.

---

## [0.12.0]

### Added
- One-time calendar auto-create mode. After a single explicit opt-in, the continuously running menu app writes pending candidates through EventKit without repeated prompts. Each EventKit note carries the SQLite candidate ID so an interrupted status update deduplicates before retry.

## [0.11.1]

### Fixed
- Structured calendar candidate extraction. Calendar extraction runs as a separate second Codex request with a strict JSON Schema after the summary succeeds. A date without a time becomes an all-day candidate; an unresolvable date is rejected. A failed extraction leaves existing pending candidates untouched and adds a visible warning to the summary.

## [0.11.0]

### Added
- Google Calendar routing and confirmation. Members can be bound to several calendars with a per-member default, and candidates are confirmed one at a time by default.

---

## [0.10.0]

### Added
- Combine XVF3800 direction with speaker evidence. Each Whisper segment carries both a voice-timbre hint and a source direction as independent evidence. Summaries gained a direction-and-speaker-hints section, and every partial and final request is required to preserve source direction.

## [0.9.0]

### Changed
- Unify the macOS identity as FamilyRecorder. All user-visible names — Privacy & Security → Microphone, Login Items & Extensions, the menu bar, and notification prompts — became consistent. `com.familyrecorder.*` remain internal identifiers only.

## [0.8.0]

### Added
- Preserve possible speakers in daily summaries. Event timelines, news, decisions, tasks, and ideas retain `可能說話者` where the source segment carried one, with a per-member section. Speaker and task owner stay distinct, and unlabeled or mixed segments are never force-assigned.

## [0.6.0]

### Added
- Event times in daily summaries. A time-output contract is appended in code on every request, requiring minute-level approximate timestamps, chronological ordering, an explicit `時間不明` marker, and forbidding substitution of the summary's own run time.

---

## Earlier releases

Version numbers for these were not recorded in the documentation. Listed newest first.

### Added
- **Configurable hallucination filtering** — relaxed, balanced, and strict presets plus an advanced threshold editor, daily rejection counts, and a `transcription_audits` table recording every accepted, filtered, empty, and failed candidate. No rule blacklists a specific sentence.
- **XVF3800 beamforming and speech energy telemetry** — read-only `diagnose-beamforming` verifying the captured UAC channel is the processed auto-selected beam, plus four-beam Speech Energy fused with software VAD and stored as a re-analyzable time series.
- **Editable daily summary prompt** — a multi-line editor in the menu bar, with the safety and output contracts still appended by the code.
- **Common-term transcription correction** — names and domain terms enter the local Whisper prompt, with conservative one-character near-miss correction afterwards.
- **One-click safe uninstaller** — a separately signed native uninstaller with keep-data and complete-removal modes, a `.familyrecorder-data` ownership marker, a refusal list for dangerous targets, and recovery via the Trash.
- **Local household speaker labeling** — 1–8 members, 15-second enrollment, features stored `0600` with the enrollment audio discarded, and conservative `recognized` / `mixed` / `uncertain` results.
- **Microphone access requested before speaker enrollment**, so a doomed recording is never started.
- **Whisper model downloads in the menu bar** — allowlisted names, resumable `.partial` downloads, and GGML validation before switching.
- **Portable macOS DMG installer** with a portable checksum.
- **macOS menu bar controls** — status, timed pause, folder shortcuts, model switching, immediate summary, diagnostics.
- **Sub-second pause** — the listener checks `control.json` once per second and discards the in-flight chunk.
- **ChatGPT login for daily summaries** — the official Codex CLI's saved session, with no OpenAI API key read or accepted.
- **Continuous recording during transcription**, so speech is not lost while Whisper runs.
- **XVF3800 capture timing fixes on macOS.**
- **Initial XVF3800 FamilyRecorder v0.1** — continuous capture, VAD gating, local whisper.cpp transcription, Markdown transcripts, and a SQLite index.
