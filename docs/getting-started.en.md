# Getting started

**English** · [繁體中文](getting-started.md) · [Back to docs index](README.en.md)

From zero to "there is a summary waiting in the morning". Roughly 30–60 minutes, most of it spent waiting for whisper.cpp to build and the model to download.

---

## Contents

- [Requirements](#requirements)
- [Option 1: graphical DMG install](#option-1-graphical-dmg-install-recommended)
- [Option 2: install from source](#option-2-install-from-source)
- [What macOS calls it](#what-macos-calls-it)
- [First hardware bring-up](#first-hardware-bring-up)
- [Installing the resident jobs](#installing-the-resident-jobs)
- [Next steps](#next-steps)

---

## Requirements

| Item | Requirement |
|---|---|
| Computer | Apple Silicon Mac (`arm64`) |
| OS | macOS 13 or newer |
| Microphone | [reSpeaker XVF3800 USB 4-Mic Array](https://github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY), VID `0x2886` / PID `0x001A` |
| Package manager | [Homebrew](https://brew.sh/) |
| Dependency | Homebrew `libusb` (installed automatically) |
| Disk | 2–4 GB for the program, models, and build; recorded data is separate |
| Network | Only cloud summaries need it. Listening, VAD, and transcription are fully offline |
| Account | For daily summaries, a ChatGPT account with Codex access. **No API key required** |

**Storage estimate:** 16 kHz mono PCM16 reaches roughly **2.8 GB/day** in the extreme case of continuous speech. Real usage is far lower because silent chunks never produce a WAV. Default retention is `keep_audio_days: 7`.

---

## Option 1: graphical DMG install (recommended)

Download the latest `FamilyRecorder-*-arm64.dmg` and its `.sha256` from [GitHub Releases](https://github.com/pcpcchen-coder/FamilyRecorder/releases).

**Verify the SHA-256 first:**

```bash
shasum -a 256 ~/Downloads/FamilyRecorder-*-arm64.dmg
cat ~/Downloads/FamilyRecorder-*-arm64.dmg.sha256
```

Once they match, open the DMG:

1. Run "**安裝 FamilyRecorder.app**" (Install FamilyRecorder).
2. Choose a local Whisper model: `small`, `medium`, or the recommended `large-v3-turbo`.
3. If Codex is not installed yet, click "**安裝官方 Codex CLI**" (Install the official Codex CLI), then "**登入 ChatGPT**" (Sign in to ChatGPT) — your browser opens the official sign-in page.
4. Click "**安裝 FamilyRecorder**". The installer installs the wheel bundled in the DMG, builds whisper.cpp with Metal, downloads the selected model, and creates the listener, summary, and menu-bar jobs.
5. Connect the XVF3800 and allow "FamilyRecorder" to use the microphone when macOS prompts.

The same DMG also ships "**解除安裝 FamilyRecorder.app**" (Uninstall FamilyRecorder). Day to day you can pick "解除安裝 FamilyRecorder…" from the menu-bar waveform icon; if the menu bar cannot start, remount the DMG and open the uninstaller — no terminal needed.

### About sign-in

The installer **never** asks for an OpenAI API key, and never reads the Codex credential file or token. It only runs the official `codex login` and `codex login status`. If the usual browser redirect is blocked by your network, use "**改用裝置碼登入**" (device-code sign-in).

Sign-in can also be done later. Recording and local transcription still install, but the daily summary schedule only activates after you **re-run the installer** once you are signed in.

### About Gatekeeper

Public DMGs target Apple Silicon and macOS 13+ and are **ad-hoc signed, not notarized with an Apple Developer ID**. If Gatekeeper blocks the first launch, right-click the installer app in Finder and choose **Open**, after confirming the download source and SHA-256.

Homebrew packages, whisper.cpp sources and models, and the Codex CLI are still downloaded from their own official sources. The FamilyRecorder wheel and the installer UI itself are contained in the DMG.

---

## Option 2: install from source

```bash
git clone https://github.com/pcpcchen-coder/FamilyRecorder.git
cd FamilyRecorder
./scripts/install_mac.sh
```

The script, in order:

1. Installs Python 3.12, PortAudio, CMake, and Git.
2. Creates `~/Library/Application Support/FamilyRecorder/venv`.
3. Installs FamilyRecorder.
4. Checks out `whisper.cpp` v1.8.1 and builds it with `GGML_METAL=ON`.
5. Downloads `ggml-large-v3-turbo.bin`.
6. Creates `~/.config/familyrecorder/config.yaml` **only if it does not exist** — an existing config is never overwritten.
7. Detects the official Codex CLI / ChatGPT app and reports the current ChatGPT sign-in status.

To test with a smaller model first:

```bash
WHISPER_MODEL=medium ./scripts/install_mac.sh
```

The script downloads it and switches `whisper.model_path` to `ggml-medium.bin`, preserving every other setting in an existing config.

### Then install the menu-bar app

Install the menu bar **before** hardware acceptance:

```bash
./scripts/install_menubar.sh
```

It uses the Swift tooling built into macOS to compile the native `FamilyRecorder.app` and the uninstaller app. The main app installs to the standard `/Applications/FamilyRecorder.app`; the Python runtime, Whisper models, and uninstaller stay under `~/Library/Application Support/FamilyRecorder`.

The installer opens the main app the same way a Finder double-click would, so macOS shows its native microphone prompt directly. The listener starts only after you allow it. Afterwards you can open FamilyRecorder from Applications like any other app.

All three internal jobs are associated with the **same app** in `/Applications`, avoiding the Spotlight/TCC identity-cache inconsistency that hidden or user-level paths cause.

---

## What macOS calls it

Since 0.9.0 every user-visible name after a proper install is consistent:

| macOS screen | Displayed name |
|---|---|
| Settings → Privacy & Security → Microphone | `FamilyRecorder.app` (macOS shows the `.app` extension on this page) |
| Settings → General → Login Items & Extensions → Allow in Background | `FamilyRecorder` (all three background jobs grouped under one app) |
| Menu bar, notifications, microphone prompts | `FamilyRecorder` |

`com.familyrecorder.listener`, `com.familyrecorder.summary`, and `com.familyrecorder.menubar` are **internal identifiers** used in logs and diagnostic commands, not names macOS shows to ordinary users.

> **Upgrading in place from 0.8.0 or older?** Legacy `python3.12` / `family-recorder` entries may remain in system lists. You can switch them off; there is no need to reset the whole list. The current recording service no longer relies on that grant — `FamilyRecorder.app` holds the microphone authorization.

---

## First hardware bring-up

Connect the XVF3800 first, then run these in order. Every command below uses these three variables:

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
APP="/Applications/FamilyRecorder.app"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
```

### Step 1: list devices

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" list-devices
```

Standard firmware usually looks like this:

```text
ID  Channels  Default Hz  Name
2   2         48000       XMOS XVF3800 Voice Processor
```

If automatic matching fails, set one of these in the YAML:

```yaml
audio:
  device_id: 2
  # or
  device_name_contains: "XMOS XVF3800 Voice Processor"
```

### Step 2: full health check

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" doctor
```

### Step 3: confirm you are capturing the right channel

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" diagnose-beamforming
```

Standard output should show the left channel as `(8, 0)` user-chosen / processed auto-selected beam (or `(6, 3)` processed auto-selected beam), ending with:

```text
[OK] FamilyRecorder is capturing the beamformed/processed left UAC channel.
```

The right channel is usually `(7, 3)` ASR/AEC residual. FamilyRecorder defaults to `audio.channels: 1` and therefore takes only the first/left channel rather than averaging two channels with different processing purposes. **The diagnostic never rewrites XVF3800 routing.**

Details in [hardware and capture](hardware.en.md).

### Step 4: grant the microphone and run one 30-second chunk

Allow `FamilyRecorder` under Settings → Privacy & Security → Microphone, then run a single capture through the native app identity. **Keep talking** once it starts, so VAD does not judge it silent:

```bash
"$APP/Contents/MacOS/FamilyRecorder" \
  --service listener-once \
  --program "$RUNTIME/venv/bin/family-recorder" \
  --config "$CONFIG"
```

### Step 5: check the result

```bash
cat "$HOME/xvf3800-listener-data/transcripts/$(date +%F).md"

sqlite3 "$HOME/xvf3800-listener-data/listener.sqlite3" \
  'select started_at, status, round(rms_dbfs,1), round(speech_ratio,2), text
   from segments order by id desc limit 5;'

sqlite3 "$HOME/xvf3800-listener-data/listener.sqlite3" \
  'select started_at, software_speech_ratio, hardware_speech_ratio, gate_reason
   from captures order by id desc limit 5;'
```

### If the chunk was skipped

`Chunk skipped by combined silence/VAD gate` means neither software VAD nor hardware Speech Energy reached its threshold. **This is correct privacy/storage behavior**, not an error. Even without a WAV, the low-volume `captures` / `acoustic_samples` telemetry is still recorded so you can see why.

While testing you can loosen the thresholds and restore them afterwards:

```yaml
vad:
  min_speech_ratio: 0.02   # temporary; default 0.08
  min_rms_dbfs: -55.0      # temporary; default -48.0
```

---

## Installing the resident jobs

> ⚠️ **Pass the single-capture acceptance above first**, and make sure `install_menubar.sh` has run, before installing the resident jobs.

```bash
./scripts/install_launchd.sh          # resident listener
./scripts/install_daily_summary.sh    # daily summary schedule
```

Check status and logs:

```bash
launchctl print "gui/$UID/com.familyrecorder.listener"
launchctl print "gui/$UID/com.familyrecorder.summary"
tail -f "$HOME/xvf3800-listener-data/logs/listener.log"
tail -f "$HOME/xvf3800-listener-data/logs/listener.error.log"
```

If the device is unplugged or temporarily unavailable, the listener retries on `audio.retry_seconds` and re-selects the device automatically once it returns.

---

## Next steps

1. **[Calibrate the room front](hardware.en.md#direction-calibration)** so `0°` means what you want it to mean.
2. **[Enroll household voice samples](speakers.en.md)** so transcripts can say who probably spoke.
3. **[Compare microphone placements](hardware.en.md#mic-placement-test)** with a real A/B/C CER measurement.
4. **[Tune the configuration](configuration.en.md)** — sensitivity, retention, summary time.
5. **[Set up Google Calendar](daily-summary.en.md#google-calendar-candidate-events)** so summary events can be added with one click.
6. **[Try a different use case](use-cases.en.md)** — study review, dream journal, idea capture.
7. **[Work through the 31-item hardware acceptance list](development.en.md#acceptance-checklist)**.

Something not working? See **[troubleshooting](troubleshooting.en.md)**.
