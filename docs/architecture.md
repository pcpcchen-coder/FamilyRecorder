# Architecture and trust boundaries

FamilyRecorder intentionally separates the always-on local path from the scheduled cloud path.

## Local listener

`AudioRecorder` selects an input, holds one PortAudio stream open, and emits fixed-duration mono PCM16 chunks. `analyze_audio` runs before a file is created. Only chunks passing both the configured RMS threshold and WebRTC VAD ratio are written to `audio/`.

`WhisperCppTranscriber` invokes `whisper-cli` as a subprocess. Successful text is appended to one date-scoped Markdown file and indexed in SQLite. A failed transcription is indexed as `failed` and keeps its WAV for diagnosis. Retention is independent of transcript retention.

## Cloud summary

`DailySummaryRunner` accepts a calendar date and opens only the corresponding Markdown file under `transcripts/`. It pipes that text to the official Codex CLI, which reuses its own saved “Sign in with ChatGPT” session. FamilyRecorder never reads the Codex authentication file and has no API-key integration. It writes the returned text under `summaries/` and indexes it in SQLite.

Each Codex invocation uses an ephemeral session, a read-only sandbox, an empty temporary working directory, and ignores user config and project rules. The prompt treats transcript content as untrusted and disallows tool use. The summary runner has no audio decoding or upload implementation. This makes the “text only” boundary testable rather than relying on a prompt instruction.

## Scheduled processes

- `com.familyrecorder.listener`: `RunAtLoad` plus `KeepAlive` after failures.
- `com.familyrecorder.summary`: `StartCalendarInterval`, with hour/minute read from YAML when the plist is installed.

Both are per-user LaunchAgents, not root daemons. No API key or Codex token is placed in launchd environment variables; the summary job only provides `HOME` so the official CLI can locate its own saved login.

## Explicit non-goals for v0.2

- Speaker identification or diarization
- Covert recording
- Live cloud transcription
- Uploading or remotely backing up raw audio
- Acting on inferred tasks or reminders
- A web dashboard
