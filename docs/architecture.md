# Architecture and trust boundaries

FamilyRecorder intentionally separates the always-on local path from the scheduled cloud path.

## Local listener

`AudioRecorder` selects an input, holds one PortAudio stream open, and emits fixed-duration mono PCM16 chunks. `analyze_audio` runs before a file is created. Only chunks passing both the configured RMS threshold and WebRTC VAD ratio are written to `audio/`.

`WhisperCppTranscriber` invokes `whisper-cli` as a subprocess. Successful text is appended to one date-scoped Markdown file and indexed in SQLite. A failed transcription is indexed as `failed` and keeps its WAV for diagnosis. Retention is independent of transcript retention.

## Cloud summary

`DailySummaryRunner` accepts a calendar date and opens only the corresponding Markdown file under `transcripts/`. It obtains an API key from macOS Keychain, calls the OpenAI Responses API with `store=False`, then writes the resulting text under `summaries/` and indexes it in SQLite.

The summary runner has no audio decoding or upload implementation. This makes the “text only” boundary testable rather than relying on a prompt instruction.

## Scheduled processes

- `com.familyrecorder.listener`: `RunAtLoad` plus `KeepAlive` after failures.
- `com.familyrecorder.summary`: `StartCalendarInterval`, with hour/minute read from YAML when the plist is installed.

Both are per-user LaunchAgents, not root daemons. Keys are never placed in launchd environment variables.

## Explicit non-goals for v0.1

- Speaker identification or diarization
- Covert recording
- Live cloud transcription
- Uploading or remotely backing up raw audio
- Acting on inferred tasks or reminders
- A web dashboard
