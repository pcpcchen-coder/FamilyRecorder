# Troubleshooting

**English** · [繁體中文](troubleshooting.md) · [Back to docs index](README.en.md)

Organized by symptom. Every command assumes these variables:

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
APP="/Applications/FamilyRecorder.app"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
DB="$HOME/xvf3800-listener-data/listener.sqlite3"
FR="$RUNTIME/venv/bin/family-recorder"
```

---

## Contents

**Hardware and capture**
[The XVF3800 is not found](#the-xvf3800-is-not-found) ·
[Invalid sample rate](#invalid-sample-rate) ·
[Beamforming diagnosis is not OK](#beamforming-diagnosis-is-not-ok) ·
[Everything keeps getting skipped by VAD](#everything-keeps-getting-skipped-by-vad) ·
[Direction shows as unreadable](#direction-shows-as-unreadable) ·
[Direction disagrees with where people are](#direction-disagrees-with-where-people-are)

**Permissions and services**
[The LaunchAgent gets no audio](#the-launchagent-gets-no-audio) ·
[FamilyRecorder is missing from the microphone list](#familyrecorder-is-missing-from-the-microphone-list) ·
[No Google Calendar authorization dialog](#no-google-calendar-authorization-dialog) ·
[Settings still shows python3.12](#settings-still-shows-python312-or-family-recorder) ·
[No menu bar icon](#no-menu-bar-icon)

**Recognition quality**
[The same caption keeps appearing during silence](#the-same-caption-keeps-appearing-during-silence) ·
[Speakers are usually uncertain or wrong](#speakers-are-usually-uncertain-or-wrong) ·
[Voice sample enrollment keeps failing](#voice-sample-enrollment-keeps-failing) ·
[Whisper is slow or the Mac gets hot](#whisper-is-slow-or-the-mac-gets-hot)

**Summaries and calendar**
[The summary never ran](#the-summary-never-ran) ·
[The summary has no event times](#the-summary-has-no-event-times) ·
[The summary dropped speaker labels](#the-summary-dropped-speaker-labels) ·
[The summary has no direction information](#the-summary-has-no-direction-information) ·
[Pending events list is empty](#the-summary-has-dates-and-events-but-the-pending-list-is-empty)

**Uninstall**
[The uninstaller finds no installation](#the-uninstaller-finds-no-installation)

---

## Hardware and capture

### The XVF3800 is not found

First confirm the device exists under **System Information → USB** and in **Audio MIDI Setup**, then run:

```bash
"$FR" --config "$CONFIG" list-devices
```

Some boards report as `XMOS XVF3800 Voice Processor` rather than just `XVF3800`. If matching fails, pin it in the YAML:

```yaml
audio:
  device_id: 2
  # or
  device_name_contains: "XMOS XVF3800 Voice Processor"
```

---

### Invalid sample rate

Confirm the YAML targets `16000`. If opening at 16 kHz fails, the program falls back to the device's declared 48 kHz and converts to 16 kHz locally.

If the device's default is wrong, set it to 16 kHz or 48 kHz in **Audio MIDI Setup** first.

---

### Beamforming diagnosis is not OK

1. **Confirm `audio.channels: 1` first.** With `2` the capture is treated as a left/right mix and cannot be verified.
2. Inspect the left channel's routing:

```bash
"$FR" --config "$CONFIG" diagnose-beamforming --json
```

Categories `1/2/3/11` are raw/intermediate microphones and **should not be used with FamilyRecorder**. The diagnostic only reads and never changes settings; if another tool changed the routing, restore the processed auto-selected beam per the XVF3800 firmware documentation.

The full interpretation table is in [hardware and capture](hardware.en.md#reading-the-result).

---

### Everything keeps getting skipped by VAD

First find out which stage rejected it:

```bash
sqlite3 "$DB" "select started_at, round(rms_dbfs,1) rms, round(snr_db,1) snr,
  round(software_speech_ratio,2) sw, round(hardware_speech_ratio,2) hw, gate_reason
  from captures order by id desc limit 20;"
```

| `gate_reason` | Means | What to do |
|---|---|---|
| `silence` | Both software and hardware judged it silent | Lower `vad.min_rms_dbfs` and `min_speech_ratio` |
| `software_vad; speech_energy_unavailable` | Hardware telemetry is unreadable | See [direction shows as unreadable](#direction-shows-as-unreadable) |
| `hallucination_filter:*` | Rejected by hallucination filtering | Switch to the relaxed preset |

Start at `-55 dBFS` / `0.02` to confirm the whole path works, then tighten gradually:

```yaml
vad:
  min_rms_dbfs: -55.0
  min_speech_ratio: 0.02
```

The [placement test](hardware.en.md#mic-placement-test) also compares capture quality between physical positions.

> If Speech Energy is always `0`, run `doctor` and **speak naturally at the microphone**. Do not treat echo from the system speakers as a reliable near-field test.

---

### Direction shows as unreadable

1. Confirm the device is a reSpeaker XVF3800 with VID `0x2886` / PID `0x001A`.
2. Install libusb: `brew install libusb`
3. Run "檢查系統狀態" (Check system status) from the menu, or `"$FR" --config "$CONFIG" doctor`.

> **Audio recording fine does not imply USB vendor control is readable.** They are two independent channels. FamilyRecorder keeps the recording and marks direction unavailable — it never stops the listener over a direction failure.

---

### Direction disagrees with where people are

1. Confirm the microphone **has not been rotated**.
2. Re-run the front calibration:

```bash
"$FR" --config "$CONFIG" calibrate-direction --seconds 4
```

Wall reflections, a television, speaker echo, simultaneous speech, or two people on the same bearing can all distort DoA. **Direction is a supporting hint, not an identity or distance sensor.**

---

## Permissions and services

### The LaunchAgent gets no audio

1. Test with the bring-up command first:

```bash
"$APP/Contents/MacOS/FamilyRecorder" \
  --service listener-once --program "$FR" --config "$CONFIG"
```

2. Confirm `FamilyRecorder.app` is enabled under **System Settings → Privacy & Security → Microphone**.
3. Check the error log:

```bash
tail -50 "$HOME/xvf3800-listener-data/logs/listener.error.log"
```

> The macOS microphone grant is an **interactive, per-machine authorization**. No install script can bypass it for you.

---

### FamilyRecorder is missing from the microphone list

Upgrade to **0.14.3 or newer** and re-run:

```bash
./scripts/install_menubar.sh
./scripts/install_launchd.sh
```

Newer versions install the main app at the standard `/Applications/FamilyRecorder.app`, include the **Audio Input entitlement** required by Hardened Runtime, and automatically remove duplicate older apps under Application Support or `~/Applications`.

After you click Allow on first launch, **fully reopen System Settings** to see `FamilyRecorder.app`. Models, transcripts, and recordings are not moved by the migration.

---

### No Google Calendar authorization dialog

Upgrade to **0.14.4 or newer**.

The 0.14.3 Hardened Runtime signature was missing the Calendar entitlement, so macOS rejected the request **before** showing the authorization dialog. 0.14.4 adds the entitlement, and the menu now shows a configured-but-unauthorized state as "需要重新授權" (*needs re-authorization*).

Your Google account, existing events, and FamilyRecorder's calendar mappings **are not deleted**.

---

### Settings still shows `python3.12` or `family-recorder`

These are **legacy entries** left by versions before 0.8.0, which launched the Python worker directly.

1. Confirm you are on 0.9.0 or newer.
2. Re-run `install_menubar.sh`, `install_launchd.sh`, and `install_daily_summary.sh`.
3. Switch the old entries off.

The active microphone entry should be `FamilyRecorder.app`, and background activity should show `FamilyRecorder`.

> ⚠️ **Do not reset every app's microphone permission just to clear one stale row.**

---

### No menu bar icon

```bash
./scripts/install_menubar.sh
launchctl print "gui/$UID/com.familyrecorder.menubar"
tail -50 "$HOME/xvf3800-listener-data/logs/menubar.error.log"
```

> Quitting from the menu is a **deliberate clean exit**, so the LaunchAgent does not immediately relaunch it. Re-run the install script or log in again.

---

## Recognition quality

### The same caption keeps appearing during silence

This is usually a **deterministic Whisper hallucination** on low-information background noise, not evidence that the model was tampered with.

1. Confirm hallucination filtering is on and set to **balanced**.
2. Check today's rejection counts and reasons:

```bash
sqlite3 "$DB" "select reason, count(*) from transcription_audits
  where decision='filtered' and date(started_at)=date('now','localtime')
  group by reason order by 2 desc;"
```

3. If things still slip through, switch to **strict**. If short, quiet, real conversation is being dropped, switch to **relaxed** and fine-tune from the advanced thresholds.

> ⚠️ **Do not blacklist a specific sentence.** Hallucinated text changes with the model and the prompt, so a blacklist goes stale quickly — which is why this project offers no sentence blacklist.

---

### Speakers are usually uncertain or wrong

**Improve the samples before changing thresholds.**

1. Have each member re-record natural speech at the **same microphone position**.
2. Avoid a television, music, or simultaneous speech.
3. Children's voices change as they grow — update their samples periodically.

Then adjust thresholds:

| Symptom | Change |
|---|---|
| Frequent misidentification | Raise `speakers.min_similarity` or `min_margin` |
| Mostly uncertain | Lower `min_similarity` **slightly** |

> ⚠️ This feature **must not** be used for access control, payments, parental surveillance, or any purpose requiring a confirmed identity.

---

### Voice sample enrollment keeps failing

Confirm FamilyRecorder is enabled under **System Settings → Privacy & Security → Microphone**.

The menu-bar app **actively checks the permission** before recording a sample; if it is not granted, it does not start a recording that is certain to fail, and offers a link to the relevant Settings page.

When enrolling from the command line, **pause the listener first**:

```bash
"$FR" --config "$CONFIG" pause
"$FR" --config "$CONFIG" enroll-speaker --name "me" --seconds 15
"$FR" --config "$CONFIG" resume
```

---

### Whisper is slow or the Mac gets hot

Switch to `medium` or `small` rather than **only raising threads**:

```bash
"$FR" --config "$CONFIG" download-whisper-model --model medium
```

Confirm the install output includes **Metal** and that `doctor` points at the correct build.

---

## Summaries and calendar

### The summary never ran

1. Check the sign-in:

```bash
codex login status
```

2. Run the same day manually:

```bash
"$FR" --config "$CONFIG" summary --date 2026-08-19
```

3. Confirm the transcript for that date actually has content and the network is reachable, then check:

```bash
tail -50 "$HOME/xvf3800-listener-data/logs/summary.error.log"
```

If the sign-in expired, run `codex login` interactively.

> The schedule **summarizes "yesterday" at 00:10 by default**. For today's summary use "立即整理今天" in the menu bar, or `summary --date "$(date +%F)"`.

---

### The summary has no event times

1. Confirm you are on **0.6.0 or newer**.
2. Re-run `summary --date YYYY-MM-DD` for that day.

**Existing summary files are never rewritten automatically.** Newer versions append the time-output rules to every single, partial, and final merge request, and existing custom prompts need no manual change.

---

### The summary dropped speaker labels

1. Confirm you are on **0.8.0 or newer**.
2. Check whether the day's transcript headings **actually contain** 可能：name / 可能多人 / 不確定.
3. Re-run the summary for that date.

If a source segment carries no speaker label, **the summary will not guess one** — that is deliberate.

---

### The summary has no direction information

Direction affects **only transcript segments produced after the upgrade**.

1. Confirm transcript headings contain 方向：… .
2. Re-run the summary for that date.

Since 0.10.0, every partial and final summary is required to preserve the source direction, and a dedicated direction-and-speaker-hints section was added.

---

### The summary has dates and events, but the pending list is empty

1. Confirm you are on **0.11.1 or newer**.
2. Re-run the summary for that day.

Newer versions extract calendar candidates in a **separate structured ChatGPT request** after the summary completes. Events with a date but no time become **all-day candidates**; events whose date cannot be resolved are skipped.

The bottom of the summary file explicitly states how many candidates were found, that none were found, or that extraction failed.

```bash
sqlite3 "$DB" "select id, summary_date, title, starts_at, status
  from calendar_candidates order by id desc limit 20;"
```

> Since 0.12.0 you can also opt in once to "auto-add after summary". When that succeeds, the pending list **empties quickly** — check Google Calendar directly.

---

## Uninstall

### The uninstaller finds no installation

Confirm you are logged in as the **same macOS user that installed FamilyRecorder**.

If only old data remains and the menu bar is broken, open "解除安裝 FamilyRecorder.app" directly from the latest DMG.

Or from a source checkout:

```bash
./scripts/uninstall_family_recorder.sh inspect
```

---

## Still stuck?

1. Run the full health check and include its output:

```bash
"$FR" --config "$CONFIG" doctor
```

2. Collect the relevant log:

```bash
tail -100 "$HOME/xvf3800-listener-data/logs/listener.error.log"
```

3. Open an issue at [GitHub Issues](https://github.com/pcpcchen-coder/FamilyRecorder/issues).

> ⚠️ **Before pasting, remove transcript content, household member names, and your username from file paths.**

---

## Related documents

- [Configuration reference](configuration.en.md) — what each parameter means
- [Hardware and capture](hardware.en.md) — diagnostic commands
- [Data and SQLite](data-model.en.md#useful-queries) — more diagnostic queries
- [Development → acceptance checklist](development.en.md#acceptance-checklist) — 31 hardware checks
