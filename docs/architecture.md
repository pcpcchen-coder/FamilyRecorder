# Architecture and trust boundaries

FamilyRecorder intentionally separates the always-on local path from the scheduled cloud path.

## Local listener

`AudioRecorder` selects an input, holds one PortAudio stream open, and emits fixed-duration mono PCM16 chunks. `analyze_audio` runs before a file is created. Only chunks passing both the configured RMS threshold and WebRTC VAD ratio are written to `audio/`.

`WhisperCppTranscriber` invokes `whisper-cli` as a subprocess. Successful text is appended to one date-scoped Markdown file and indexed in SQLite. A failed transcription is indexed as `failed` and keeps its WAV for diagnosis. Retention is independent of transcript retention.

When household speakers are enabled, the same in-memory PCM is divided into short windows and reduced to normalized spectral, pitch, and timing features. Those vectors are compared only with intentionally enrolled local profiles. The result is a conservative whole-chunk hint (`recognized`, `mixed`, or `uncertain`), not word-level diarization or authentication. Enrollment audio is never written; JSON feature profiles are mode `0600` under `speaker-profiles/`.

## Cloud summary

`DailySummaryRunner` accepts a calendar date and opens only the corresponding Markdown file under `transcripts/`. It pipes that text to the official Codex CLI, which reuses its own saved “Sign in with ChatGPT” session. FamilyRecorder never reads the Codex authentication file and has no API-key integration. It writes the returned text under `summaries/` and indexes it in SQLite.

Transcript headings carry local chunk ranges such as `19:40:00–19:40:30`. A mandatory time-output contract is appended in code independently of the configurable summary prompt. It requires minute-level approximate timestamps, a chronological event timeline, explicit `時間不明` markers, and forbids replacing source time with summary-generation time. The same contract is present in every partial request and the final merge, so chunking cannot silently discard chronology.

The same request path appends an independent speaker-output contract. When a heading carries `可能：name`, `可能多人`, or `不確定`, important timeline events, news, decisions, commitments, tasks, and ideas retain that attribution with explicitly uncertain wording. A separate household-member section groups relevant content by possible speaker. Speaker and task owner remain distinct, and unlabeled or mixed chunks cannot be assigned to a person. Long transcripts split only between complete `### time — speaker` segments, so partial summarization cannot detach speech from its local time/speaker heading; the final merge receives the contract again.

Each Codex invocation uses an ephemeral session, a read-only sandbox, an empty temporary working directory, and ignores user config and project rules. The prompt treats transcript content as untrusted and disallows tool use. The summary runner has no audio decoding or upload implementation. This makes the “text only” boundary testable rather than relying on a prompt instruction.

## Scheduled processes

- `com.familyrecorder.listener`: `RunAtLoad` plus `KeepAlive` after failures.
- `com.familyrecorder.summary`: `StartCalendarInterval`, with hour/minute read from YAML when the plist is installed.
- `com.familyrecorder.menubar`: native AppKit status item, started in the Aqua login session and restarted only after unexpected exits.

All three are per-user LaunchAgents, not root daemons. No API key or Codex token is placed in launchd environment variables; the summary job only provides `HOME` so the official CLI can locate its own saved login.

## Menu bar control path

The Swift menu bar app invokes the installed `family-recorder` CLI for status, pause/resume, targeted YAML edits, summaries, diagnostics, and intentional speaker enrollment. Enrollment temporarily pauses the listener, opens the microphone through the same Python capture path, retains PCM only in memory until features are saved, and resumes only if the menu itself initiated the pause. Pause state is atomically persisted as `data_dir/control.json`; the listener checks it before opening a stream and during capture. A chunk overlapping a newly requested pause is discarded.

Whisper model choices are discovered from already-downloaded `ggml-*.bin` files. Targeted config edits preserve unrelated YAML comments and values. Switching the local model requires a listener restart, while the Codex summary model is read fresh for every summary run.

## Uninstall boundary

The menu bar opens a separately signed native uninstaller instead of deleting its own runtime inline. The uninstaller can therefore stop all three LaunchAgents before moving the running menu app, Python environment, whisper.cpp checkout, and models to a timestamped Trash folder. A second mode also moves the configured data and config roots; the first preserves them for reinstall.

New data roots contain a `.familyrecorder-data` ownership marker. The helper rejects `/`, the user home directory, Trash, and the LaunchAgents directory as removal targets. For an older or custom unmarked data root, it moves only known FamilyRecorder-owned children and leaves unrelated files in place. Removal is recoverable until the user empties Trash. Shared ChatGPT/Codex authentication and Homebrew packages are explicitly outside the uninstall boundary.

## Explicit non-goals

- Biometric-grade speaker identification, authentication, or word-level diarization
- Covert recording
- Live cloud transcription
- Uploading or remotely backing up raw audio
- Acting on inferred tasks or reminders
- A web dashboard
