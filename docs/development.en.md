# Development and testing

**English** · [繁體中文](development.md) · [Back to docs index](README.en.md)

---

## Contents

- [Local development](#local-development)
- [Testing strategy](#testing-strategy)
- [Code structure](#code-structure)
- [Building the DMG](#building-the-dmg)
- [Acceptance checklist](#acceptance-checklist)

---

## Local development

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest --cov=family_recorder
```

The project requires Python 3.11 or newer. `ruff` is configured with line-length 100, target `py311`, and the `E`, `F`, `I`, `UP`, `B`, `SIM` rule sets.

### Dependencies

| Package | Purpose |
|---|---|
| `numpy` | Audio analysis and feature extraction |
| `PyYAML` | Configuration |
| `pyusb` | XVF3800 USB vendor control |
| `sounddevice` | PortAudio bindings |
| `webrtcvad-wheels` | WebRTC VAD |

Development additionally needs `build`, `pytest`, `pytest-cov`, and `ruff`.

---

## Testing strategy

**CI does not depend on physical hardware.** All of the following have isolated tests:

- Device selection and scoring
- Routing response decoding, beamformed vs. raw determination
- Four-beam float32 Speech Energy parsing
- Software/hardware VAD fusion
- Shared time-series alignment
- Stereo downmix and sample-rate conversion
- Whisper CLI invocation and JSON parsing
- SQLite migrations and Markdown appending
- Approximate speaker classification
- Retention
- The text-only summary path
- CER reporting
- Acoustic-layer and text-layer hallucination filtering
- Atomic pause-state read/write
- Uninstaller safety checks
- macOS identity consistency

```bash
.venv/bin/pytest tests/test_listener.py -v      # gate decisions
.venv/bin/pytest tests/test_summary.py -v       # text-only boundary and contracts
.venv/bin/pytest tests/test_hallucination.py -v # hallucination filtering
.venv/bin/pytest tests/test_uninstaller.py -v   # uninstall safety checks
```

> ⚠️ **Before a release, still run** `diagnose-beamforming`, `doctor`, and speech/silence sampling **on real XVF3800 hardware.** Passing CI does not prove the device path works — see the [acceptance checklist](#acceptance-checklist) below.

### CI

`.github/workflows/ci.yml` runs on every pull request and every push to `main`:

1. `ruff check .`
2. `ruff format --check .`
3. `pytest --cov=family_recorder`
4. `python -m build` (wheel and sdist)

---

## Code structure

```text
src/family_recorder/
├── config.py           # YAML schema and defaults; the root of all dependencies
├── devices.py          # macOS input device enumeration and scoring
├── audio.py            # AudioRecorder, downmix, resampling, WAV I/O
├── metrics.py          # RMS, SNR, VAD ratio, low-frequency ratio, tonality
├── transcriber.py      # whisper-cli subprocess and JSON parsing
├── direction.py        # XVF3800 USB control, DoA, Speech Energy, circular clustering
├── speakers.py         # Feature extraction, profile storage, approximate labeling
├── hallucination.py    # Acoustic-layer and text-layer rejection logic
├── control.py          # control.json pause state
├── storage.py          # SQLite schema/migrations, Markdown, retention
├── listener.py         # The resident main loop
├── summary.py          # Daily summary, output contracts, calendar extraction
├── placement.py        # Placement test and CER
├── model_manager.py    # Model catalog, download, validation
├── config_editor.py    # Targeted YAML edits preserving comments
└── cli.py              # All subcommands; the single entry point
```

Dependencies are **deliberately one-directional**: lower modules never import higher ones. The full graph is in [architecture → module map](architecture.en.md#module-map).

### Other directories

| Directory | Contents |
|---|---|
| `menubar/` | Swift menu-bar app sources, `Info.plist`, entitlements |
| `packaging/` | Swift installer and uninstaller, payload script |
| `launchd/` | plist templates for the three LaunchAgents |
| `scripts/` | Install, uninstall, and DMG build scripts |
| `tests/` | 17 test files |

---

## Building the DMG

On an Apple Silicon Mac:

```bash
./scripts/build_dmg.sh
```

The output is `dist/FamilyRecorder-<version>-arm64.dmg` and its `.sha256`.

> For public distribution without a Gatekeeper "not notarized" warning, the publisher must also sign with a **Developer ID Application certificate** and submit the build for Apple **notarization**. An ordinary Apple Development certificate is **not** equivalent.

---

## Acceptance checklist

Thirty-one checks to run on real hardware before a release. This list doubles as the project's specification for what counts as correct behavior.

### Basic capture

1. `list-devices` shows the XVF3800/XMOS and `doctor` selects the right device.
2. After `listen --once` the WAV is 16 kHz, mono, PCM16.
3. Thirty seconds of silence produces no WAV or transcript; continuous speech does.
4. The day's Markdown has correct time headings and Chinese content.
5. The newest SQLite row has `status='transcribed'` with sensible RMS and speech ratio.
6. Unplugging the XVF3800 makes the listener log retries; reconnecting recovers.
7. Temporarily setting `keep_audio_days` to 0 and running `cleanup` removes old WAVs without touching transcripts.

### Summary and privacy boundary

8. A manual `summary --date ...` produces only a Markdown summary, and the cloud code path reads no WAV or voice features.
9. `codex login status` and `doctor` both report signed in, while YAML, plists, environment variables, and Python dependencies contain no OpenAI API key.

### Services and menu bar

10. After a reboot or re-login, all three `launchctl print` jobs exist and the FamilyRecorder icon is in the menu bar.
11. Pausing from the menu stops chunk production; resuming continues the listener. The model list and folder shortcuts work.

### Placement test

12. The A/B/C placement report includes per-sentence transcription, RMS, SNR, speech ratio, CER, and a summary table.

### Speaker labels

13. With three test members enrolled, the menu shows 3/3; transcripts show 可能：name or conservatively 可能多人 / 不確定, and the three SQLite speaker columns stay in sync.
14. Deleting one member's sample removes the corresponding `speaker-*.json` and leaves other members unaffected.

### Summary contracts

15. The summary's event timeline, news, decisions, and tasks all preserve `約 HH:MM` or a time range; anything untraceable is marked 時間不明.
16. Every important item with a source speaker keeps 可能說話者, and a per-member section exists. Multiple, uncertain, and unlabeled content is not force-assigned, and a speaker never automatically becomes a task owner.
17. With the test transcript forced into multiple parts, each part still carries its `### time — 可能：name` heading, and the final merge request carries the same speaker contract.

### Uninstall and packaging

18. Both uninstall modes verified in an isolated temporary HOME: keep-mode leaves transcripts and settings untouched; full mode removes all FamilyRecorder content; an unmarked shared folder retains unrelated files.
19. The DMG contains both the installer and the uninstaller, and their signatures, versions, and bundled scripts all validate.
20. `ruff check .`, `ruff format --check .`, `pytest`, the Swift typecheck, plist/shell syntax, and the package build all pass.

### Direction telemetry

21. `doctor` reports XVF3800 direction telemetry OK, and the menu's "test current direction" returns an angle while speaking.
22. After calibrating the front, one sentence each from front, left, and right yields transcript angles near `0°`, `90°`, and `270°`, with direction summaries and per-sample rows in SQLite.
23. Alternating between two directions within one 30-second chunk gives each Whisper segment its matching direction; simultaneous or rapidly overlapping speech is conservatively marked multiple/uncertain.
24. The daily summary includes the direction-and-speaker-hints section and preserves source direction on important items, never assigning a member on direction alone.

### Calendar

25. No Google Calendar event is created before confirmation by default; enabling `auto_create` requires one explicit opt-in. Member routing falls back to the member and household defaults, both automatic and manual creation update SQLite status, and a restart-and-retry never adds the same candidate twice.

### Beamforming and Speech Energy

26. `diagnose-beamforming` reads back left and right `AUDIO_MGR_OP`; with the default mono setting it reports `[OK]` and the left channel is category `6` processed or category `8` user-chosen auto-selected beam, not a raw category.
27. On real hardware, all four `AEC_SPENERGY_VALUES` beams are near 0 during silence; speech produces non-zero energy on at least one beam and the auto-selected beam, and `doctor` shows all four values readable.
28. SQLite `captures` has rows for both silent and speech chunks; `acoustic_samples` resolves DoA and four-beam energy by the same `capture_id + offset_ms`, and `gate_reason='xvf3800_speech_energy'` when hardware energy rescues a software VAD miss.

### Hallucination filtering

29. With steady noise at 0% hardware Speech Energy, roughly 10–25% software VAD, and SNR below 10 dB, `captures.gate_reason` is `hallucination_filter:hardware_silence` and no transcript is produced.
30. For two identical long sentences 30 seconds apart, the first is accepted and the second is written as `transcription_audits.decision='filtered'` without appending to Markdown; short interjections are unaffected by this rule.
31. The menu shows today's rejection counts, and relaxed/balanced/strict plus advanced threshold changes persist to YAML and restart the listener successfully.

---

## Related documents

- [Architecture](architecture.en.md) — each module's responsibility and the data flow
- [CLI reference](cli.en.md) — the commands used while testing
- [Data and SQLite](data-model.en.md#useful-queries) — acceptance queries
- [Contributing guide](../CONTRIBUTING.en.md) — pull request flow and conventions
