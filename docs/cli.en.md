# CLI reference

**English** · [繁體中文](cli.md) · [Back to docs index](README.en.md)

`family-recorder` is the single entry point for the whole system. The menu-bar app, the LaunchAgents, and the install scripts all act through it, so every graphical action has a command-line equivalent.

---

## Invocation

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
FR="$RUNTIME/venv/bin/family-recorder"

"$FR" --config "$CONFIG" <command> [options]
```

### Global options

| Option | Default | Description |
|---|---|---|
| `--config PATH` | `~/.config/familyrecorder/config.yaml` | Config file location |
| `--verbose` | off | Verbose logging |

> `xvf-listener` is an alias for the same entry point.

---

## Diagnostics and status

| Command | Description |
|---|---|
| `list-devices` | List macOS audio input devices with IDs, channel counts, and default sample rates |
| `doctor` | Check configuration and runtime dependencies: device selection, whisper.cpp paths, model, Codex login status, direction telemetry |
| `diagnose-beamforming` | **Read-only** verification that the captured UAC channel really is beamformed/processed |
| `probe-direction` | Sample and display XVF3800 direction telemetry without writing to the transcript |

```bash
"$FR" --config "$CONFIG" list-devices
"$FR" --config "$CONFIG" doctor
"$FR" --config "$CONFIG" diagnose-beamforming --json
"$FR" --config "$CONFIG" probe-direction --seconds 2
```

| Option | Command | Default | Description |
|---|---|---|---|
| `--json` | `diagnose-beamforming` | off | Machine-readable JSON output |
| `--seconds N` | `probe-direction` | `2.0` | Sampling duration |

---

## Recording

| Command | Description |
|---|---|
| `listen` | Run the resident listener. In production this is invoked by the LaunchAgent |
| `listen --once` | Process one chunk and exit. **Use this for bring-up acceptance** |
| `pause` | Pause microphone capture |
| `pause --minutes N` | Pause for N minutes, then resume automatically |
| `resume` | Resume capture |

```bash
"$FR" --config "$CONFIG" listen --once
"$FR" --config "$CONFIG" pause --minutes 60
"$FR" --config "$CONFIG" resume
```

Pause state is written to `data_dir/control.json`. The listener checks it once per second and closes the microphone stream within about a second. **The in-flight chunk is discarded, never saved.**

> ⚠️ For real bring-up, run through the native app identity so the macOS microphone grant applies:
> ```bash
> /Applications/FamilyRecorder.app/Contents/MacOS/FamilyRecorder \
>   --service listener-once --program "$FR" --config "$CONFIG"
> ```

---

## Summaries

| Command | Description |
|---|---|
| `summary` | Summarize **yesterday** in the Mac's local date, same as the daily schedule |
| `summary --date YYYY-MM-DD` | Summarize a specific date |

```bash
"$FR" --config "$CONFIG" summary
"$FR" --config "$CONFIG" summary --date 2026-08-19
"$FR" --config "$CONFIG" summary --date "$(date +%F)"   # summarize today
```

Re-running a day **overwrites** `summaries/YYYY-MM-DD.md` and updates the same date row in the SQLite `summaries` table, rather than creating conflicting duplicates.

---

## Models and prompts

| Command | Description |
|---|---|
| `set-whisper-model --path PATH` | Switch to an already-downloaded whisper.cpp model |
| `download-whisper-model --model NAME` | Download, verify, and select a multilingual model |
| `set-summary-model --model NAME` | Set the Codex summary model. An empty string uses the account default |
| `set-summary-prompt --prompt TEXT` | Set the editable summary instructions |
| `reset-summary-prompt` | Restore the built-in summary instructions |
| `set-common-terms --term T [--term T ...]` | Set names and terms that improve local transcription |

```bash
"$FR" --config "$CONFIG" download-whisper-model --model small-q5_1
"$FR" --config "$CONFIG" set-whisper-model --path "$RUNTIME/whisper.cpp/models/ggml-medium.bin"
"$FR" --config "$CONFIG" set-summary-model --model ""       # back to the account default
"$FR" --config "$CONFIG" set-common-terms --term "陳樂融" --term "quadratic function"
```

Model names are validated against an allowlist, sourced from the Hugging Face repository named by whisper.cpp's official download script. Incomplete downloads are kept as `.partial` for resumption, and the switch happens only after GGML format validation. **Existing models are never deleted.**

`set-common-terms` **replaces** the whole list rather than appending. Switching models or terms restarts the listener.

---

## Hallucination filtering

| Command | Description |
|---|---|
| `set-hallucination-preset --name {relaxed,balanced,strict}` | Apply one of the three presets |
| `set-hallucination-filter [thresholds]` | Adjust thresholds individually |

```bash
"$FR" --config "$CONFIG" set-hallucination-preset --name strict
"$FR" --config "$CONFIG" set-hallucination-filter \
  --min-avg-logprob -0.70 --repeat-window-seconds 600
```

`set-hallucination-filter` updates only the fields you name and leaves the rest unchanged. Options map one-to-one onto the YAML fields, with underscores replaced by hyphens:

**Boolean** (`true` / `false`): `--enabled`, `--hardware-silence-guard-enabled`, `--adaptive-noise-enabled`, `--low-frequency-filter-enabled`, `--whisper-confidence-enabled`, `--suppress-non-speech-tokens`, `--repeat-filter-enabled`

**Integer**: `--noise-window-chunks`, `--noise-min-samples`, `--repeat-window-seconds`, `--max-repetitions`, `--min-repeat-text-chars`

**Float**: `--hardware-silence-max-ratio`, `--hardware-silence-max-software-speech-ratio`, `--hardware-silence-max-snr-db`, `--noise-margin-db`, `--low-frequency-min-ratio`, `--tonal-energy-min-ratio`, `--no-speech-probability-max`, `--min-avg-logprob`, `--low-probability-threshold`, `--max-low-probability-ratio`, `--max-compression-ratio`, `--repeat-similarity-threshold`

Each field is explained in the [configuration reference](configuration.en.md#hallucination_filter).

---

## Household members and voices

| Command | Description |
|---|---|
| `set-speakers --name N [--name N ...]` | Set the known household members (1–8) |
| `enroll-speaker --name N` | Record a temporary sample and save only its local voice features |
| `delete-speaker-profile --name N` | Delete one member's local feature profile |

```bash
"$FR" --config "$CONFIG" set-speakers --name "me" --name "family-2" --name "family-3"
"$FR" --config "$CONFIG" pause
"$FR" --config "$CONFIG" enroll-speaker --name "me" --seconds 15
"$FR" --config "$CONFIG" resume
```

| Option | Default | Description |
|---|---:|---|
| `--seconds N` | `15` | Recording duration |
| `--delay N` | `2.0` | Countdown before recording starts |

> ⚠️ **Run `pause` before `enroll-speaker`**, otherwise the listener holds the microphone. The menu bar handles this automatically.

Enrollment audio exists only in memory and is discarded once features are computed — **no WAV is created**. `set-speakers` replaces the whole roster.

---

## Direction

| Command | Description |
|---|---|
| `set-direction-enabled --enabled {true,false}` | Turn XVF3800 direction telemetry on or off |
| `calibrate-direction` | Make the current speaking position the room front (0°) |
| `probe-direction` | Sample and display direction telemetry |

```bash
"$FR" --config "$CONFIG" calibrate-direction --seconds 4
"$FR" --config "$CONFIG" set-direction-enabled --enabled false
```

| Option | Default | Description |
|---|---:|---|
| `--seconds N` | `4.0` (calibrate) / `2.0` (probe) | Sampling duration |

---

## Google Calendar

| Command | Description |
|---|---|
| `set-calendar-enabled --enabled {true,false}` | Turn candidate extraction on or off |
| `set-calendar-auto-create --enabled {true,false}` | Create events automatically after a one-time opt-in |
| `set-calendar-default --calendar-id ID --calendar-name NAME` | Set the household default calendar |
| `set-member-calendar --member M --calendar-id ID --enabled {true,false}` | Assign or unassign a calendar for one member |
| `set-member-calendar-default --member M --calendar-id ID` | Choose that member's fallback calendar |
| `calendar-event-created --id N [--external-id ID]` | Mark a candidate as created |
| `dismiss-calendar-event --id N` | Dismiss a pending candidate |

```bash
"$FR" --config "$CONFIG" set-calendar-default \
  --calendar-id "abc@group.calendar.google.com" --calendar-name "Family"
"$FR" --config "$CONFIG" set-member-calendar \
  --member "family-2" --calendar-id "xyz@gmail.com" --calendar-name "Personal" --enabled true
"$FR" --config "$CONFIG" dismiss-calendar-event --id 42
```

`--calendar-name` is optional for `set-member-calendar`. A member's fallback calendar **must be one already assigned to that member**, or config validation fails.

`calendar-event-created` and `dismiss-calendar-event` are normally invoked by the menu-bar app after user confirmation and rarely needed by hand. Candidate IDs come from SQLite:

```sql
select id, title, starts_at, member_name from calendar_candidates where status='pending';
```

---

## Testing and maintenance

| Command | Description |
|---|---|
| `placement-test --positions A B C` | Compare several microphone positions |
| `cleanup` | Apply the configured raw-audio retention now |

```bash
"$FR" --config "$CONFIG" placement-test --positions "coffee-table" "shelf" "next-to-mac"
"$FR" --config "$CONFIG" placement-test --positions A B --seconds 10 --sentences-file ./s.txt
"$FR" --config "$CONFIG" cleanup
```

| Option | Default | Description |
|---|---|---|
| `--positions ...` | `A B C` | Position names; any number |
| `--seconds N` | From `placement_test.recording_seconds_per_sentence` | Recording duration per sentence |
| `--sentences-file PATH` | Built-in 20 sentences | Custom fixed sentences (UTF-8, one per line) |

---

## Internal commands

| Command | Description |
|---|---|
| `menu-status` | Machine-readable status output for the menu-bar app. **Not a stable public interface** |

---

## Related documents

- [Configuration reference](configuration.en.md) — the YAML fields each command modifies
- [Hardware and capture](hardware.en.md) — full detail on the diagnostic and calibration commands
- [Menu bar and services](menu-bar.en.md) — the graphical equivalents
- [Troubleshooting](troubleshooting.en.md) — using these commands to diagnose problems
