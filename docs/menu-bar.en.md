# Menu bar and services

**English** · [繁體中文](menu-bar.md) · [Back to docs index](README.en.md)

After installation a round waveform icon appears in the top-right corner. Day-to-day use almost never requires a terminal — uninstalling included.

---

## Contents

- [Icon states](#icon-states)
- [Menu actions](#menu-actions)
- [How pause works](#how-pause-works)
- [The three LaunchAgents](#the-three-launchagents)
- [One-click uninstall](#one-click-uninstall)

---

## Icon states

| Icon | Meaning |
|---|---|
| Round waveform | Recording |
| Pause symbol | Paused |
| Warning symbol | The listener is failing or not running |

---

## Menu actions

### Status and data

- Shows **recording / paused / service not running**, plus the current Whisper and summary models.
- Quick links to **today's transcript** and **summary**.
- Opens the folders holding **all data, audio, logs, and the config file**.

### Pause

- Pause for **15 minutes**, **1 hour**, or **until manually resumed**.

### Local Whisper

- Switch models from the list of **already-downloaded** `ggml-*.bin` files. Switching restarts the listener.
- "**下載其他模型…**" (Download other models) offers new multilingual models in three groups:
  - Standard
  - Quantized (space-saving)
  - Legacy compatibility

  It shows an estimated size, supports resuming after a failure, and switches and restarts the listener only after **GGML format validation** passes. **Existing models are never deleted.**

The list mirrors the official whisper.cpp v1.8.1 model catalog. FamilyRecorder defaults to Chinese, so **`.en` English-only builds are not shown**; Tiny, Base, Small, Medium, Large v1/v2/v3, Large v3 Turbo, and their multilingual Q5/Q8 quantized variants are available. Models come from the Hugging Face repository named by whisper.cpp's official download script, names are validated against an **allowlist**, and incomplete files are kept as `.partial` for resumption.

From the command line:

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  download-whisper-model --model small-q5_1
```

### Change model → ChatGPT summary

- Use the ChatGPT account's default model, or enter a custom Codex model name your account can actually use.
- Customize the daily summary prompt in a **multi-line editor**, or restore the built-in format with one click.

Changes apply only to summaries generated or re-run afterwards. The summary model is read fresh on every run, so **no restart is needed**.

### Common-term correction

Maintain names and terminology line by line. Saving **restarts the listener** to apply them.

Terms enter the local Whisper prompt, and unambiguous one-character near misses are conservatively corrected afterwards. **Used locally only — never sent to the cloud.**

### Hallucination filtering

- View **today's acoustic and text rejection counts**.
- Choose **relaxed, balanced, or strict** protection.
- "**進階調整門檻…**" (Advanced thresholds) edits every percentage, SNR, log probability, and repetition-window value directly.

Changes restart the listener. The actual values behind each preset are in the [configuration reference](configuration.en.md#the-three-presets).

### Household members and voices

- Edit the member roster.
- View enrollment status (for example `3/3`).
- **Record, update, or delete** individual voice samples.

Before recording, the app **actively checks microphone authorization**; if it is not granted, it does not start a recording that is certain to fail, and offers a direct link to the relevant Settings page. The listener pauses during recording and resumes automatically afterwards.

See [speakers and direction](speakers.en.md).

### Sound direction

- Turn direction detection on or off.
- "**測試目前方向…**" (Test current direction) reports bearing, angle, stability, and valid sample count without writing to the transcript.
- "**把目前位置校準為正前方…**" (Calibrate this position as front) sets the room's `0°` from where the speaker stands.

See [hardware and capture → direction calibration](hardware.en.md#direction-calibration).

### Google Calendar

- Choose the household default calendar.
- Assign several calendars to each member and set their default.
- Confirm AI candidate events one by one, or opt in once for automatic creation.

See [daily summary and calendar](daily-summary.en.md#google-calendar-candidate-events).

### Actions

- **立即整理今天** (Summarize today now) — passes today's date explicitly, rather than the scheduled "yesterday".
- **Restart the recording service**
- **Run the full `doctor` check**
- **解除安裝 FamilyRecorder…** (Uninstall) — opens the standalone uninstaller.

### Quitting the menu bar app

Quitting **closes only the icon; it does not stop the listener**. This is a deliberate clean exit, so the LaunchAgent does not immediately relaunch it. Log in again or re-run `install_menubar.sh` to bring it back.

---

## How pause works

Pause state lives in `data_dir/control.json`, **not just in UI memory**.

| Behavior | Detail |
|---|---|
| Response time | The listener checks once per second and closes the microphone stream within about **one second** |
| The in-flight chunk | **Discarded, never saved** |
| Menu-bar app restart | Never accidentally resumes recording |
| Timed pause expiry | The listener **resumes automatically** |
| Menu-bar app quit | The pause remains in effect |

Command-line equivalents:

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" pause --minutes 60
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" resume
```

---

## The three LaunchAgents

All are **per-user LaunchAgents**, not root daemons.

| Identifier | Trigger | Responsibility |
|---|---|---|
| `com.familyrecorder.listener` | `RunAtLoad` plus `KeepAlive` after failures | Resident capture and transcription |
| `com.familyrecorder.summary` | `StartCalendarInterval`, hour and minute read from YAML | Daily summary |
| `com.familyrecorder.menubar` | Starts at login, restarted only after unexpected exits | Native AppKit status item |

```bash
launchctl print "gui/$UID/com.familyrecorder.listener"
launchctl print "gui/$UID/com.familyrecorder.summary"
launchctl print "gui/$UID/com.familyrecorder.menubar"

tail -f "$HOME/xvf3800-listener-data/logs/listener.log"
tail -f "$HOME/xvf3800-listener-data/logs/listener.error.log"
tail -f "$HOME/xvf3800-listener-data/logs/summary.error.log"
tail -f "$HOME/xvf3800-listener-data/logs/menubar.error.log"
```

Restart the listener manually:

```bash
launchctl kickstart -k "gui/$UID/com.familyrecorder.listener"
```

> ⚠️ After changing `summary.hour` / `summary.minute`, **re-run `./scripts/install_daily_summary.sh`** so the plist is updated.

No API key or Codex token appears in launchd environment variables; the summary job provides only `HOME` so the official CLI can locate its own saved login.

All three jobs are associated with the **same app** in `/Applications`, avoiding the Spotlight/TCC identity-cache inconsistency that hidden or user-level paths cause.

---

## One-click uninstall

### The recommended path

1. Click the menu-bar waveform icon → "**解除安裝 FamilyRecorder…**" (Uninstall FamilyRecorder).
2. Choose a mode:
   - "**Remove the program only, keep household data and settings**"
   - "**Complete removal, including all models, recordings, and records**"
3. Review the listed **sizes** for program/models, household data, and settings, then confirm.
4. Everything selected moves to a **single Trash subfolder**; empty the Trash once you are sure you do not need it back.

Cleanup continues even after the menu closes — the uninstaller is a **separately signed program**, which is why it can stop all three LaunchAgents before moving the running menu-bar app.

### The difference between the two modes

| Content | Program only | Complete removal |
|---|:---:|:---:|
| The three LaunchAgents | ✅ Stopped and removed | ✅ |
| Python runtime, menu-bar app, uninstaller | ✅ | ✅ |
| whisper.cpp and all local models | ✅ | ✅ |
| Raw WAVs, transcripts, summaries, SQLite | ❌ **Kept** | ✅ |
| Voice features, placement tests, pause state, logs | ❌ **Kept** | ✅ |
| `config.yaml` and its install backups | ❌ **Kept** | ✅ |
| Microphone and calendar permission records | ❌ Kept | ✅ |

"Program only" keeps `data_dir` and `config.yaml` so reinstalling later is easy.

### Explicitly outside the boundary

**Neither mode** will:

- Sign out of or remove **ChatGPT / Codex**
- Delete **Homebrew, Python, Git, CMake, or PortAudio**, which other programs may share
- Delete the **GitHub repo, a local source checkout**, or separately downloaded DMGs

### Safety mechanisms

| Mechanism | Effect |
|---|---|
| `.familyrecorder-data` marker | Lets the uninstaller confirm this is a FamilyRecorder-owned folder |
| Unmarked paths | Only **known** children and the database are moved — never an entire Documents or other shared folder |
| Refusal list | Refuses `/`, the user home directory, Trash, and the LaunchAgents directory as removal targets |
| Move to Trash | **Recoverable until you empty the Trash** |

### From source

If the graphical path is unavailable:

```bash
./scripts/uninstall_family_recorder.sh inspect
./scripts/uninstall_family_recorder.sh uninstall keep-data  # keep household data and settings
./scripts/uninstall_family_recorder.sh uninstall all        # complete removal
```

The older `./scripts/uninstall_launchd.sh` **only stops and removes the three LaunchAgents temporarily** and deletes nothing else.

If the menu bar itself is broken, you can also open "解除安裝 FamilyRecorder.app" directly from the latest DMG.

---

## Related documents

- [CLI reference](cli.en.md) — the command-line equivalent of every menu action
- [Architecture → menu bar control path](architecture.en.md#menu-bar-control-path) — sequence diagram
- [Architecture → uninstall boundary](architecture.en.md#uninstall-boundary)
- [Troubleshooting → no menu bar icon](troubleshooting.en.md#no-menu-bar-icon)
