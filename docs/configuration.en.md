# Configuration reference

**English** · [繁體中文](configuration.md) · [Back to docs index](README.en.md)

Config file: `~/.config/familyrecorder/config.yaml`
Full example: [`config.example.yaml`](../config.example.yaml)

The install scripts create the config **only when it does not exist** and never overwrite an existing one. Most fields can also be changed from the menu bar, which preserves unrelated YAML comments and values.

---

## Contents

- [audio](#audio) · [vad](#vad) · [whisper](#whisper) · [hallucination_filter](#hallucination_filter)
- [storage](#storage) · [speakers](#speakers) · [direction](#direction)
- [calendar](#calendar) · [summary](#summary) · [placement_test](#placement_test)
- [Do I need to restart after changing this?](#do-i-need-to-restart-after-changing-this)

---

## `audio`

| Field | Default | Description |
|---|---:|---|
| `device_name_contains` | `"XVF3800"` | Case-insensitive device-name match. When this exact substring is unavailable, `XVF3800`, `XMOS`, `USB`, and `array` are also scored |
| `device_id` | `null` | Pin a PortAudio device ID directly. Takes precedence over name matching |
| `allow_default_input` | `false` | Whether to fall back to the system default (usually the built-in mic) when no XVF/XMOS/USB device is found. **Off by default**, so it never silently records the built-in microphone |
| `sample_rate` | `16000` | Target sample rate. If the device refuses it, capture uses the device default and converts locally |
| `channels` | `1` | **Keep this at `1`.** Setting `2` downmixes left and right, destroying the beamformed signal, and `diagnose-beamforming` reports `ambiguous_stereo_downmix` |
| `chunk_seconds` | `30` | Length of each continuous capture chunk |
| `retry_seconds` | `10` | Retry interval when the device is unplugged or temporarily unavailable |

---

## `vad`

The first speech decision layer. **It decides only whether to keep a chunk, never what the text says.**

| Field | Default | Description |
|---|---:|---|
| `enabled` | `true` | With this off, every chunk is kept and sent to Whisper — disk usage and compute rise sharply |
| `aggressiveness` | `2` | WebRTC VAD strength. `0` is most permissive, `3` most aggressive |
| `frame_ms` | `30` | VAD analysis frame length: 10, 20, or 30 |
| `min_speech_ratio` | `0.08` | Minimum fraction of frames in a chunk that must be judged speech |
| `min_rms_dbfs` | `-48.0` | Loudness gate. **Closer to 0 is stricter**; `-55` is more permissive than `-48` |

**Tuning:**

| Symptom | Change |
|---|---|
| Real conversation keeps getting skipped | Lower `min_speech_ratio` (e.g. `0.04`) and `min_rms_dbfs` (e.g. `-54`) |
| Room noise keeps getting recorded | Raise both, or raise `aggressiveness` |
| Only want close-range speech | Raise `min_rms_dbfs` (e.g. `-40`) |

Start at `-55` / `0.02` to confirm the hardware path works at all, then tighten. Watch `captures.gate_reason` to see which stage actually rejected a chunk.

---

## `whisper`

| Field | Default | Description |
|---|---|---|
| `binary_path` | `…/whisper.cpp/build/bin/whisper-cli` | The whisper.cpp executable |
| `model_path` | `…/models/ggml-large-v3-turbo.bin` | The local model. Switchable from the menu bar |
| `language` | `"zh"` | Whisper language code |
| `threads` | `8` | Decode threads. If it gets slow or hot, **switch to a smaller model** rather than only raising this |
| `initial_prompt` | Chinese household-conversation hint | Guidance prompt for local Whisper |
| `common_terms` | `[]` | Names and domain terms. They enter the local prompt, and unambiguous one-character near misses of terms with three or more characters are conservatively corrected afterwards |
| `extra_args` | `[]` | Additional arguments passed to `whisper-cli` |

`common_terms` is used locally only and never sent to the cloud. Maintain it from the menu bar under "常用字詞校正" (common-term correction).

---

## `hallucination_filter`

Multi-layer hallucination protection. **No rule blacklists any specific sentence** — hallucinated text changes with the model and prompt, so blacklists go stale; the decisions use statistical properties instead.

The decision order is documented in [architecture](architecture.en.md#recognition-path-whisper-and-text-filtering).

### The three presets

The menu bar offers three presets. They differ as follows (fields not listed are identical across all three):

| Field | relaxed | balanced (default) | strict |
|---|---:|---:|---:|
| `hardware_silence_max_ratio` | `0.01` | `0.01` | `0.03` |
| `hardware_silence_max_software_speech_ratio` | `0.20` | `0.30` | `0.40` |
| `hardware_silence_max_snr_db` | `6.0` | `10.0` | `14.0` |
| `noise_margin_db` | `1.0` | `3.0` | `5.0` |
| `low_frequency_min_ratio` | `0.75` | `0.65` | `0.55` |
| `tonal_energy_min_ratio` | `0.45` | `0.35` | `0.25` |
| `no_speech_probability_max` | `0.60` | `0.60` | `0.50` |
| `min_avg_logprob` | `-1.00` | `-0.80` | `-0.60` |
| `low_probability_threshold` | `0.15` | `0.15` | `0.20` |
| `max_low_probability_ratio` | `0.25` | `0.15` | `0.10` |
| `max_compression_ratio` | `2.80` | `2.40` | `2.20` |
| `repeat_window_seconds` | `180` | `300` | `600` |
| `max_repetitions` | `2` | `1` | `1` |
| `repeat_similarity_threshold` | `0.99` | `0.96` | `0.92` |
| `min_repeat_text_chars` | `8` | `5` | `4` |

**Relaxed**: when you fear losing real but quiet speech (dream journaling, for instance).
**Balanced**: general household use.
**Strict**: quiet rooms with steady background noise where repeated hallucinated captions keep appearing.

### Every field

| Field | Default | Description |
|---|---:|---|
| `enabled` | `true` | Off leaves only the basic VAD gate |
| **Acoustic layer** | | |
| `hardware_silence_guard_enabled` | `true` | Let hardware silence veto a software-VAD false positive |
| `hardware_silence_max_ratio` | `0.01` | Speech Energy at or below this ratio counts as hardware silence |
| `hardware_silence_max_software_speech_ratio` | `0.30` | During hardware silence, software VAD below this counts as weak evidence |
| `hardware_silence_max_snr_db` | `10.0` | During hardware silence, SNR must also be at or below this to veto, so one sensor cannot drop real speech |
| `adaptive_noise_enabled` | `true` | Enable the rolling-median noise floor |
| `noise_window_chunks` | `120` | History window for the noise floor |
| `noise_min_samples` | `4` | Minimum samples before the floor takes effect |
| `noise_margin_db` | `3.0` | How many dB above the floor still counts as near-baseline |
| `low_frequency_filter_enabled` | `true` | Enable low-frequency / narrow-tonal detection |
| `low_frequency_min_ratio` | `0.65` | Threshold for the 80–300 Hz energy share |
| `tonal_energy_min_ratio` | `0.35` | Threshold for the share of energy in a few fixed frequencies |
| **Whisper text layer** | | |
| `whisper_confidence_enabled` | `true` | Enable token-confidence checks |
| `no_speech_probability_max` | `0.60` | Rejection threshold for no-speech probability; also passed to the whisper.cpp decoder |
| `min_avg_logprob` | `-0.80` | Lower bound on average token log probability. **Closer to 0 is stricter** |
| `low_probability_threshold` | `0.15` | Probability below which a token counts as low-confidence |
| `max_low_probability_ratio` | `0.15` | Maximum share of low-confidence tokens in one passage |
| `max_compression_ratio` | `2.40` | Upper bound on compression ratio for excessively repetitive text |
| `suppress_non_speech_tokens` | `true` | Suppress non-speech tokens |
| **Cross-chunk layer** | | |
| `repeat_filter_enabled` | `true` | Enable cross-chunk repeated-sentence filtering |
| `repeat_window_seconds` | `300` | How far back to look |
| `max_repetitions` | `1` | How many times an identical or near-identical sentence may already appear in the window |
| `repeat_similarity_threshold` | `0.96` | Normalized-text similarity at or above which two passages count as duplicates |
| `min_repeat_text_chars` | `5` | Only text at least this long is repeat-filtered, so short interjections are unaffected |

Every rejection is written to SQLite's `transcription_audits`, including the raw candidate text and the reason.

---

## `storage`

| Field | Default | Description |
|---|---:|---|
| `data_dir` | `~/xvf3800-listener-data` | Root of all data. New directories get a `.familyrecorder-data` ownership marker |
| `keep_audio_days` | `7` | WAV retention in days. `0` keeps only files not yet past the current cutoff |
| `delete_audio_after_transcription` | `false` | Delete the WAV immediately after a successful or empty transcription. **Failed WAVs are always kept** for diagnosis |

Run retention manually:

```bash
family-recorder --config "$CONFIG" cleanup
```

Retention affects `audio/` only. Transcripts, summaries, SQLite telemetry, and audit rows are untouched.

---

## `speakers`

| Field | Default | Description |
|---|---:|---|
| `enabled` | `false` | Turned on automatically by the menu once members exist |
| `members` | `[]` | Known member names, 1–8 people |
| `min_similarity` | `0.82` | Minimum feature similarity. **Raising it reduces misidentification but increases "uncertain"** |
| `min_margin` | `0.025` | How far ahead the top match must be over the runner-up |
| `dominance_threshold` | `0.65` | Share of analysis windows in a segment that must agree on the primary candidate |

Names live only in this Mac's private YAML and never need to enter a public repo. See [speakers and direction](speakers.en.md).

---

## `direction`

| Field | Default | Description |
|---|---:|---|
| `enabled` | `true` | Read XVF3800 direction telemetry alongside audio. Capture continues if it fails |
| `sample_interval_seconds` | `0.25` | Sampling interval — four times per second by default |
| `front_angle_degrees` | `0.0` | Which raw angle represents the room's front. **Set this by menu calibration**, not by hand |
| `min_speech_samples` | `3` | Minimum speech-flagged direction samples needed for one text segment |
| `cluster_tolerance_degrees` | `35.0` | Angular tolerance when merging nearby directions |
| `multiple_direction_min_ratio` | `0.25` | Share of speech samples a second direction needs before the segment is labeled multi-direction |
| `speech_energy_enabled` | `true` | Read four-beam Speech Energy and fuse it with software VAD |
| `speech_energy_min_ratio` | `0.08` | Minimum share of non-zero auto-selected-beam samples in a chunk |
| `speech_energy_min_rms_dbfs` | `-55.0` | Local RMS floor that must **still** be met even when hardware says speech |
| `speech_energy_threshold` | `0.0` | Values above this count as hardware speech; the official definition treats any non-zero value as possible speech |
| `usb_timeout_ms` | `1000` | USB control timeout |

See [hardware and capture](hardware.en.md).

---

## `calendar`

| Field | Default | Description |
|---|---|---|
| `provider` | `"google"` | The only currently supported provider |
| `enabled` | `false` | Turned on by the menu once a default calendar is chosen |
| `auto_create` | `false` | **Requires one explicit opt-in.** Once on, summary candidates are written to the calendar automatically; can be turned off at any time |
| `default_calendar_id` | `""` | Calendar used for whole-household events or when the member cannot be determined |
| `default_calendar_name` | `""` | Display name for the above |
| `calendar_names` | `{}` | Mapping from calendar ID to display name |
| `member_calendar_ids` | `{}` | The calendars each member may use |
| `member_default_calendar_ids` | `{}` | Per-member fallback when routing is uncertain. **Must be one of the calendars already assigned to that member** |

FamilyRecorder **stores no Google password or OAuth token**. It writes through the Google account you already added under macOS Internet Accounts and synced in the Calendar app. See [daily summary and calendar](daily-summary.en.md#google-calendar-candidate-events).

---

## `summary`

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Set to `false` to disable cloud summaries entirely and keep only local transcripts |
| `provider` | `"codex"` | The only currently supported provider |
| `model` | `""` | Empty means the default Codex model available to the signed-in ChatGPT account. Set a value to pin a model |
| `codex_binary_path` | `"codex"` | Searches PATH, ChatGPT.app, and common Homebrew locations |
| `timeout_seconds` | `900` | Maximum wait for each Codex summary run |
| `hour` / `minute` | `0` / `10` | Daily LaunchAgent time. **Re-run `install_daily_summary.sh` after changing it** |
| `max_input_chars` | `300000` | Beyond this the transcript is split into parts, then merged and de-duplicated once |
| `prompt` | Built-in Chinese format | Customize what the summary emphasizes. **Safety rules and the time / speaker / direction contracts are still appended by the code** |

> **Important:** the scheduled run summarizes **yesterday**. To summarize today, use "立即整理今天" (summarize today now) in the menu bar, or run `summary --date $(date +%F)`.

`summary.prompt` can be edited in the menu bar under "更換模型 → ChatGPT 摘要" with a multi-line editor, or restored to the built-in format with one click. Changes apply only to summaries generated or re-run afterwards.

---

## `placement_test`

| Field | Default | Description |
|---|---:|---|
| `recording_seconds_per_sentence` | `8` | Recording duration per sentence |
| `sentences_file` | `""` | Custom fixed-sentence file (UTF-8, one per line). Empty uses the built-in 20 |

See [hardware and capture → mic placement test](hardware.en.md#mic-placement-test).

---

## Do I need to restart after changing this?

| What changed | What to do |
|---|---|
| `audio.*`, `vad.*`, `whisper.*`, `hallucination_filter.*`, `speakers.*`, `direction.*` | **Restart the listener.** Use "重新啟動錄音服務" in the menu bar, or `launchctl kickstart -k "gui/$UID/com.familyrecorder.listener"` |
| `summary.model`, `summary.prompt` | No restart. Read fresh on every summary run |
| `summary.hour` / `summary.minute` | **Re-run `./scripts/install_daily_summary.sh`** so the plist is updated |
| `storage.keep_audio_days` | Takes effect at the next retention run, or run `cleanup` now |
| `calendar.*` | No restart. The menu bar app reads the latest settings |

Changes made through the menu bar handle these restarts automatically. **You only need to restart manually when editing the YAML by hand.**

---

## Related documents

- [Architecture](architecture.en.md) — where each parameter takes effect
- [Hardware and capture](hardware.en.md) — how to measure capture-related parameters
- [Troubleshooting](troubleshooting.en.md) — symptom-oriented tuning advice
- [Use-case guide](use-cases.en.md) — recommended setting combinations per scenario
