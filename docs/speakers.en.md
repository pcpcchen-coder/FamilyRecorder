# Speakers and direction

**English** · [繁體中文](speakers.md) · [Back to docs index](README.en.md)

FamilyRecorder answers "who probably said this?" with **two independent pieces of evidence**: local voice-timbre similarity, and the hardware-reported source direction. Both are shown side by side and **never substitute for each other**.

> ⚠️ This is **not** identity verification. It must not be used for access control, payments, parental surveillance, or any purpose requiring a confirmed identity.

---

## Contents

- [What this feature does](#what-this-feature-does)
- [Enrolling household members](#enrolling-household-members)
- [How the decision works](#how-the-decision-works)
- [How direction sits alongside timbre](#how-direction-sits-alongside-timbre)
- [Tuning the thresholds](#tuning-the-thresholds)
- [Privacy](#privacy)

---

## What this feature does

It is designed specifically for a **small, fixed, known** set of household members — not general-purpose diarization or speaker verification.

| | It can | It cannot |
|---|---|---|
| **Timbre** | Judge whether audio **resembles** an enrolled member | Confirm identity, do forensic word-level voiceprints, recognize anyone not enrolled |
| **Direction** | Report the source **angle** relative to the microphone | Say who it is, how far away, or where in the room |

After Whisper finishes a 30-second chunk, its JSON timestamps split the audio into text segments **usually a few seconds long**, and each segment's audio range is compared separately on timbre, spectral, and pitch features. This is far finer than labeling one person per 30 seconds, but it remains *Whisper-segment level*, not forensic voiceprinting — **misidentification remains possible**.

---

## Enrolling household members

### From the menu bar (recommended)

1. FamilyRecorder menu → **家庭成員與人聲** (Household members and voices) → **設定家庭成員…** (Set members).
2. One member per line. **Names live only in this Mac's private YAML** and never need to enter a public repo.
3. Select each member → **錄製聲音樣本…** (Record a voice sample).
4. On first use, allow FamilyRecorder to use the microphone when macOS prompts.
5. After you start, a floating window shows the sample text, remaining time, and current status through the countdown and the 15-second recording. **The recording service pauses automatically and resumes when finished.**

### From the command line

The listener **must be paused first**, or it holds the microphone:

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
FR="$RUNTIME/venv/bin/family-recorder"

"$FR" --config "$CONFIG" set-speakers --name "me" --name "family-2" --name "family-3"
"$FR" --config "$CONFIG" pause
"$FR" --config "$CONFIG" enroll-speaker --name "me" --seconds 15
"$FR" --config "$CONFIG" resume
```

### Recording advice

| Advice | Why |
|---|---|
| Stand where you normally speak | Distance and room reflections affect the features |
| Use a natural volume and pace | Deliberately slow or loud speech produces unrepresentative features |
| Keep the room quiet | Background voices or a television contaminate the features |
| Re-record when the room, mic position, or your voice changes noticeably | Features are relative to the conditions at enrollment |
| **Update children's samples periodically** | Children's voices change markedly as they grow |

Delete one member's sample:

```bash
"$FR" --config "$CONFIG" delete-speaker-profile --name "family-2"
```

Or choose "delete voice sample" in the menu. Deletion affects only that member.

---

## How the decision works

For each Whisper text segment:

1. Slice the PCM covering that segment's time range.
2. Extract a normalized **spectral, pitch, and timing** feature vector.
3. Compare it by cosine similarity against **intentionally enrolled** local profiles only.
4. A name is shown only when all three conditions hold **simultaneously**:

| Condition | Config field | Default |
|---|---|---:|
| Top similarity is high enough | `speakers.min_similarity` | `0.82` |
| The top match leads the runner-up by enough | `speakers.min_margin` | `0.025` |
| Enough analysis windows in the segment agree | `speakers.dominance_threshold` | `0.65` |

### Result states

| `speaker_status` | Shown in the transcript | Meaning |
|---|---|---|
| `recognized` | `可能：<name>（87%）` | All three conditions met |
| `mixed` | `可能多人` (*possibly multiple*) | Several people at once, or windows disagree |
| `uncertain` | `不確定` (*uncertain*) | Similarity, margin, or consistency fell short |
| `disabled` | Nothing shown | `speakers.enabled` is `false` |

`speaker_confidence` is **local feature similarity**, not a statistically calibrated identity probability. 87% does not mean "an 87% chance this is that person".

Simultaneous speech, a television, excessive distance, or low confidence all produce 可能多人 or 不確定 — **this conservatism is deliberate**.

---

## How direction sits alongside timbre

The XVF3800 reports DoA angles through a separate USB control interface. Direction and timbre are presented as **two independent pieces of evidence for the same time segment**, never as a seat-to-name binding.

```markdown
### 19:40:07–19:40:12 — 可能：爸爸（87%） — 方向：左側 92°；穩定度 80%

明天記得去拿包裹。
```

### Why they are shown together

| Situation | Result |
|---|---|
| Dad moves to a different seat | **The name still comes from timbre**; the direction follows the new source position |
| Two people on the same bearing | Direction cannot separate them; timbre still might |
| Two clear directions | Marked as multiple; never collapsed onto the primary speaker |
| Timbre and direction conflict | The summary conservatively flags it for human confirmation |
| No timbre-derived name | **A member is never assigned on direction alone** |

Direction can corroborate timbre and reveal a change of speaker within one 30-second chunk — but **direction cannot map a location to a person**.

### Sources of interference

Wall reflections, a television, speaker echo, simultaneous speech, or two people on the same bearing can all distort DoA. **Direction is a supporting hint, not an identity or distance sensor.**

Calibration and testing are covered in [hardware and capture → direction calibration](hardware.en.md#direction-calibration).

---

## Tuning the thresholds

| Symptom | Change |
|---|---|
| **Frequent misidentification** | Raise `min_similarity` (e.g. `0.86`) or `min_margin` (e.g. `0.04`) |
| **Mostly "uncertain"** | Lower `min_similarity` only **slightly** (e.g. `0.79`). Check sample quality first |
| **Frequent "possibly multiple"** | Raising `dominance_threshold` is stricter; usually the real cause is several people or a television in the room |

Before changing thresholds, these usually help more:

1. Have each member re-record natural speech at the **same microphone position**.
2. Avoid a television, music, or simultaneous speech during enrollment.
3. Use the [placement test](hardware.en.md#mic-placement-test) to confirm the microphone position itself is good.

**Lowering thresholds directly increases misidentification.** Since a wrong name enters both the transcript and the cloud summary, prefer conservatism.

Restart the listener after changing these (menu-bar changes handle it automatically).

---

## Privacy

| Aspect | How it works |
|---|---|
| **Enrollment audio** | Lives only in memory and is discarded once features are computed. **No WAV is created** |
| **Feature files** | Mode `0600`, at `speaker-profiles/speaker-<hash>.json` |
| **Playability** | Feature vectors **cannot be converted back into audio** |
| **Cloud** | Features are **never** sent to Whisper, Codex, or any cloud service |
| **Names** | Stored in local YAML only. The cloud summary sees names as text inside transcript headings |
| **Deletion** | Deleting a member or their voice sample removes the corresponding file |

> ⚠️ Voice features are still **sensitive personal data**. They cannot be turned back into audio, but they are enough to tell whether two recordings are the same person. Protect this Mac's account credentials and its backups — Time Machine and iCloud backups include them.

Enrollment must be a **deliberate act** — the system never builds a profile for anyone from ordinary recordings. Anyone not enrolled always reads as "uncertain".

Full threat model in [privacy and trust boundaries](privacy.en.md).

---

## Related documents

- [Architecture → per-segment enrichment](architecture.en.md#per-segment-enrichment-speaker-and-direction) — sequence diagram and implementation detail
- [Configuration → speakers](configuration.en.md#speakers) · [→ direction](configuration.en.md#direction)
- [Hardware and capture](hardware.en.md) — direction telemetry and calibration
- [Data and SQLite](data-model.en.md#segments) — speaker and direction columns
- [Troubleshooting](troubleshooting.en.md#speakers-are-usually-uncertain-or-wrong)
