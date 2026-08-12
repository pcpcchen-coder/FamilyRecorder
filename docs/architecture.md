# Architecture and trust boundaries

FamilyRecorder intentionally separates the always-on local path from the scheduled cloud path.

## Local listener

`AudioRecorder` selects an input, holds one PortAudio stream open, and emits fixed-duration mono PCM16 chunks. With the default `audio.channels: 1`, CoreAudio/PortAudio captures the first (left) UAC channel. `diagnose-beamforming` reads `AUDIO_MGR_OP_L/R` without modifying the device and verifies that this channel is category 6 processed beamformed data or category 8's copy of the processed auto-selected beam. Stereo downmix is treated as ambiguous because the right channel can carry ASR/AEC-residual data.

`analyze_audio` computes RMS, WebRTC VAD, low-frequency energy ratio, and narrow tonal concentration before a file is created. In parallel, the XVF3800 auto-selected beam Speech Energy provides independent hardware speech evidence. A software miss can be rescued only when the configured fraction of auto-selected energy samples is above the firmware speech threshold and local RMS is above `speech_energy_min_rms_dbfs`. A software pass is rejected only when the hardware reports silence and both the software speech ratio and SNR remain weak. If control telemetry is unavailable, a rolling median noise floor plus tonal/low-frequency evidence can reject near-baseline stationary noise without aborting capture.

`WhisperCppTranscriber` invokes `whisper-cli` as a subprocess and reads full JSON segment timestamps plus token probabilities. Decoder no-speech/log-probability thresholds, aggregate token log probability, low-probability-token ratio, compression ratio, and a persistent cross-chunk similarity window form the second filter layer. Successful text is appended to one date-scoped Markdown file and indexed in SQLite at Whisper-segment granularity. Accepted, filtered, empty, and failed candidates are independently recorded in `transcription_audits`; filtered text never enters Markdown or the cloud-summary input. A failed transcription is indexed as `failed` and keeps its WAV for diagnosis. Retention is independent of transcript retention.

When household speakers are enabled, each Whisper-timed PCM slice is reduced to normalized spectral, pitch, and timing features. Those vectors are compared only with intentionally enrolled local profiles. The result is a conservative segment hint (`recognized`, `mixed`, or `uncertain`), not word-level diarization or authentication. Enrollment audio is never written; JSON feature profiles are mode `0600` under `speaker-profiles/`.

`DirectionSampler` runs alongside each 30-second CoreAudio capture and reads both `DOA_VALUE` and `AEC_SPENERGY_VALUES` at a configurable interval. One `AcousticSample` row owns the capture-relative millisecond offset plus optional DoA/speech flag and four beam values (focused 1, focused 2, free-running, auto-selected). A failure in either command leaves nullable fields without discarding the other command's result.

Every completed chunk, including one rejected as silence, is indexed in `captures`; its complete local time series is stored in `acoustic_samples`. Transcribed `segments.capture_id` links Whisper intervals back to the capture. After Whisper returns segment offsets, direction samples are also sliced to the same interval, circularly clustered, rotated by the room-front calibration, and stored as a segment summary plus compatibility rows in `direction_samples`. Telemetry failures never abort UAC recording or local transcription.

Speaker and direction results remain independent evidence. A stable direction can corroborate a voice label and reveal changes within one 30-second chunk, but it cannot map a location to a person. Multiple significant direction clusters are retained as `multiple`; they are not collapsed to the primary voice label.

## Cloud summary

`DailySummaryRunner` accepts a calendar date and opens only the corresponding Markdown file under `transcripts/`. It pipes that text to the official Codex CLI, which reuses its own saved “Sign in with ChatGPT” session. FamilyRecorder never reads the Codex authentication file and has no API-key integration. It writes the returned text under `summaries/` and indexes it in SQLite.

Transcript headings carry local chunk ranges such as `19:40:00–19:40:30`. A mandatory time-output contract is appended in code independently of the configurable summary prompt. It requires minute-level approximate timestamps, a chronological event timeline, explicit `時間不明` markers, and forbids replacing source time with summary-generation time. The same contract is present in every partial request and the final merge, so chunking cannot silently discard chronology.

The same request path appends independent speaker- and direction-output contracts. When a heading carries `可能：name`, `可能多人`, `不確定`, or a direction label, important timeline events, news, decisions, commitments, tasks, and ideas retain those source hints with explicitly uncertain wording. Separate household-member and direction/evidence sections group relevant content. Speaker and task owner remain distinct, direction alone cannot supply a missing name, and unlabeled or mixed segments cannot be assigned to a person. Long transcripts split only between complete `### time — speaker — direction` segments, so partial summarization cannot detach speech from its local evidence heading; the final merge receives both contracts again.

When Google Calendar candidates are enabled, calendar extraction is a separate second Codex request after the human-readable summary succeeds. That request uses `--output-schema` with a strict JSON Schema, receives only the summary and transcript text, and never creates an external event. A date without a known time becomes an all-day candidate; a date that cannot be resolved is rejected. Valid candidates are normalized and placed in SQLite as `pending`. The default path requires explicit per-event confirmation through EventKit. An optional `auto_create` path requires one explicit opt-in, after which the continuously running menu app notices pending rows and writes them through EventKit without repeated prompts. Each EventKit note carries the SQLite candidate ID so an interrupted status update can be deduplicated before retry. A failed or malformed extraction leaves existing pending candidates untouched and adds a visible warning to the Markdown summary.

Each Codex invocation uses an ephemeral session, a read-only sandbox, an empty temporary working directory, and ignores user config and project rules. The prompt treats transcript content as untrusted and disallows tool use. The summary runner has no audio decoding or upload implementation. This makes the “text only” boundary testable rather than relying on a prompt instruction.

## Scheduled processes

- `com.familyrecorder.listener`: `RunAtLoad` plus `KeepAlive` after failures.
- `com.familyrecorder.summary`: `StartCalendarInterval`, with hour/minute read from YAML when the plist is installed.
- `com.familyrecorder.menubar`: native AppKit status item, started in the Aqua login session and restarted only after unexpected exits.

All three are per-user LaunchAgents, not root daemons. No API key or Codex token is placed in launchd environment variables; the summary job only provides `HOME` so the official CLI can locate its own saved login.

## Menu bar control path

The Swift menu bar app invokes the installed `family-recorder` CLI for status, pause/resume, targeted YAML edits, summaries, diagnostics, and intentional speaker enrollment. Enrollment temporarily pauses the listener, opens the microphone through the same Python capture path, retains PCM only in memory until features are saved, and resumes only if the menu itself initiated the pause. Pause state is atomically persisted as `data_dir/control.json`; the listener checks it before opening a stream and during capture. A chunk overlapping a newly requested pause is discarded.

Whisper model choices are discovered from already-downloaded `ggml-*.bin` files. Targeted config edits preserve unrelated YAML comments and values. The anti-hallucination submenu exposes relaxed, balanced, and strict presets, daily acoustic/text rejection counts, and an advanced native threshold editor. Changing its values or the local model restarts the listener, while the Codex summary model is read fresh for every summary run.

## Uninstall boundary

The menu bar opens a separately signed native uninstaller instead of deleting its own runtime inline. The uninstaller can therefore stop all three LaunchAgents before moving the running menu app, Python environment, whisper.cpp checkout, and models to a timestamped Trash folder. A second mode also moves the configured data and config roots; the first preserves them for reinstall.

New data roots contain a `.familyrecorder-data` ownership marker. The helper rejects `/`, the user home directory, Trash, and the LaunchAgents directory as removal targets. For an older or custom unmarked data root, it moves only known FamilyRecorder-owned children and leaves unrelated files in place. Removal is recoverable until the user empties Trash. Shared ChatGPT/Codex authentication and Homebrew packages are explicitly outside the uninstall boundary.

## Explicit non-goals

- Biometric-grade speaker identification, authentication, or word-level diarization
- Treating DoA as identity, distance, room coordinates, or proof that one person spoke an entire segment
- Covert recording
- Live cloud transcription
- Uploading or remotely backing up raw audio
- Acting on inferred tasks or reminders
- A web dashboard
