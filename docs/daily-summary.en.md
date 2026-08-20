# Daily summary and calendar

**English** · [繁體中文](daily-summary.md) · [Back to docs index](README.en.md)

This is the only path that leaves this Mac: **once a day, transcript text only.**

---

## Contents

- [What the summary contains](#what-the-summary-contains)
- [Time, speaker, and direction contracts](#time-speaker-and-direction-contracts)
- [Sign-in and manual runs](#sign-in-and-manual-runs)
- [The text-only boundary](#the-text-only-boundary)
- [How long transcripts are split](#how-long-transcripts-are-split)
- [Customizing the summary prompt](#customizing-the-summary-prompt)
- [Google Calendar candidate events](#google-calendar-candidate-events)

---

## What the summary contains

The default output is Traditional Chinese Markdown containing:

1. **Event timeline** — approximate times and likely speakers preserved
2. **Per-member highlights** — grouped by the likely speakers that actually appear in the transcript
3. **Direction and speaker hints** — time, likely speaker, and source direction on one line
4. **Important news of the day**
5. **Decisions and commitments**
6. **Tasks** — likely speaker, explicitly assigned owner, time raised, and deadline kept separate
7. **Ideas worth following up**
8. **Key entities** — people, projects, product names
9. **Segments that may be misrecognized or need human confirmation**
10. **A summary of the day in 100 characters or fewer**

### From transcript to summary

**Source transcript:**

```markdown
### 19:40:07–19:40:12 — 可能：家人二（87%） — 方向：左側 92°；穩定度 80%

明天記得去拿包裹，九點前要出門。
```

**Resulting summary:**

```markdown
## 事件時間軸

- 約 19:40｜可能說話者：家人二｜來源方向：左側 92°：提到明天要拿包裹，並希望九點前出門。

## 待辦事項

- 約 19:40｜可能說話者：家人二：明天拿包裹；預計九點前出門。負責人需確認。
```

Note the last line — 負責人需確認 (*owner needs confirmation*). **A speaker never automatically becomes the owner of a task.**

---

## Time, speaker, and direction contracts

Three contracts are **appended by the code on every request**, independently of your customized `summary.prompt`. They take effect after an upgrade even if an existing `config.yaml` carries an older or custom prompt.

### The time contract

| Rule | Detail |
|---|---|
| Source of time | The **segment headings** in the daily transcript — never the cloud model's guess |
| Precision | Minute-level only, prefixed with 約 (*approximately*) |
| Spanning segments | An event across adjacent segments may show `約 19:40–19:41` |
| No match | Must be marked **時間不明** (*time unknown*) |
| Prohibited | **Never substitute the summary's run time for source time**, and never infer time from conversational content |

`19:40:07–19:40:12` is the audio time range of a Whisper text segment. It **does not mean every word carries forensic-grade timing**. All times follow the recording Mac's local date and timezone.

### The speaker contract

| Rule | Detail |
|---|---|
| Wording | Always 可能說話者 (*likely speaker*), never a confirmed identity |
| Multiple people | An event spanning members may list several, or be marked 可能多人 (*possibly multiple*) |
| Uncertainty | When confidence is low, keep 不確定 (*uncertain*) or "speaker not provided" |
| Separation | **Speaker ≠ task owner.** A speaker label only means the likely dominant voice in that segment |
| Prohibited | Unlabeled or mixed segments **must not be forced** onto any member |

### The direction contract

| Rule | Detail |
|---|---|
| What it is | Direction is an **angle relative to the microphone, not a person's name** |
| Presentation | When a segment has both stable timbre and stable direction, both are listed as mutual corroboration |
| Prohibited | **A segment without a timbre-derived name is never assigned to a member on direction alone** |
| Interference | Members moving, two people on the same bearing, wall reflections, a television, or simultaneous speech can all distort direction |

---

## Sign-in and manual runs

### One-time sign-in

Use the official Codex CLI to sign in to ChatGPT through your browser:

```bash
codex login
codex login status
```

If only the ChatGPT macOS app is installed, FamilyRecorder also finds the official Codex bundled inside it. `doctor` should report:

```text
ChatGPT login: Logged in using ChatGPT
```

Codex stores and refreshes that session itself. **FamilyRecorder never opens its credential file, and never places a token in YAML, a plist, or a log.**

### Manual runs

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"

"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" summary --date 2026-08-19
```

Without `--date`, it summarizes **yesterday** in the Mac's local date, matching the daily schedule.

> **Want today?** Use "立即整理今天" (summarize today now) in the menu bar, or pass today's date explicitly:
> ```bash
> "$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" summary --date "$(date +%F)"
> ```

Re-running a day **overwrites** `summaries/YYYY-MM-DD.md` and updates the same date row in the SQLite `summaries` table.

---

## The text-only boundary

Summarization uses the official non-interactive mode `codex exec`. Every invocation is fixed to:

| Flag | Effect |
|---|---|
| `--ephemeral` | Leaves no session state |
| `--sandbox read-only` | Read-only sandbox |
| Empty temporary working directory | A fresh empty directory every run |
| No user MCP or project rules | Unaffected by other local configuration |

The prompt itself also forbids **tool use** and **following instructions embedded in the transcript**.

The privacy boundary is a **structural property of the code**, not a promise in a prompt:

| Protection | Mechanism |
|---|---|
| No audio read | The `summary` command opens only `transcripts/YYYY-MM-DD.md` |
| No voice features read | `audio/` and `speaker-profiles/` are never opened |
| Not in the process list | The transcript reaches Codex over **stdin**, never as process arguments |
| No credential file read | Only the official `codex login status` is executed |
| No upload implementation | The summary code path contains **no audio decoding or upload implementation at all** |

> ⚠️ **Transcript text can still contain sensitive content, approximate speaker names, and household events.** Review the prompt, your ChatGPT data settings, and the household's agreement before enabling it. To skip cloud summarization entirely, set `summary.enabled: false` — recording and local transcripts are unaffected.

References: [Codex authentication](https://learn.chatgpt.com/docs/auth), [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex config reference](https://learn.chatgpt.com/docs/config-file/config-reference).

---

## How long transcripts are split

Beyond `summary.max_input_chars` (300,000 by default), the transcript is split into parts, summarized separately, then merged and de-duplicated once.

**Splits happen only between complete `### time — speaker — direction` segments**, so a heading is never separated from its content. Each part preserves event times, likely speakers, and uncertainty first; only then are the intermediate results merged.

**The time, speaker, and direction contracts appear in every partial request and in the final merge**, so chunking can never silently discard chronology or speaker attribution.

---

## Customizing the summary prompt

Edit it from the menu bar under "**更換模型 → ChatGPT 摘要**" with a multi-line editor, or restore the built-in format with one click. From the command line:

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  set-summary-prompt --prompt "$(cat my-prompt.txt)"

"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" reset-summary-prompt
```

Changes apply **only to summaries generated or re-run afterwards**; existing summary files are never rewritten. To apply a new prompt to an older date, re-run `summary --date` for it.

> Replacing the prompt is the main way to turn FamilyRecorder into a different service. Full templates for study sheets and dream journals are in the [use-case guide](use-cases.en.md).

Safety rules and the time/speaker/direction contracts are **still appended by the code**; a custom prompt cannot bypass them.

### The summary model

Leaving `summary.model` empty uses the default model available to the account. Setting a value makes FamilyRecorder pass an explicit `--model` that overrides the default, matching the precedence in the official Codex config reference.

The summary model is **read fresh on every run**, so changing it requires no service restart.

---

## Google Calendar candidate events

Google Calendar is supported by default, but FamilyRecorder **stores no Google password or OAuth token**. It uses the Google account you already added under macOS Internet Accounts and synced in the Calendar app. On first use, macOS asks for `FamilyRecorder`'s calendar permission.

### Setup

1. If the Mac has no Google account yet, go to **System Settings → Internet Accounts → Add Account → Google** and enable Calendars.
2. FamilyRecorder menu → **Google Calendar** → **連接／選擇預設 Google Calendar…** (connect / choose the default calendar).
3. Under **家庭成員日曆對應** (member calendar mapping), check one or more calendars for each member, then choose that member's **default calendar** below.
4. The daily summary — or "summarize today now" — first produces the human-readable summary, then runs **one structured candidate-extraction request** with a fixed JSON schema.
5. The default is **per-event confirmation**: review title, time, member, and target calendar in the pending list, then confirm, re-route, or skip.
6. To stop confirming daily, choose "**摘要後自動加入…**" (auto-add after summary), read the explanation, and click "agree and enable" once.

### How candidates are produced

| Case | Handling |
|---|---|
| Date and time both clear | A normal candidate event |
| Date clear, no time (e.g. "exam tomorrow") | An **all-day candidate** |
| Date not resolvable | **Skipped** — never guessed |
| Member determinable | Routing suggested from member names and calendar display names |
| Member uncertain | Falls back to the member default, then the household default |

### Automatic mode

With `auto_create` on, both existing pending events and future summary events are added automatically, usually within **10 seconds** of the summary finishing. You can turn it off from the same menu at any time and return to per-event confirmation.

Every EventKit note carries the **candidate ID**, so a restart or an interrupted status update deduplicates before retrying rather than creating the event twice.

### Failure handling

If the second, structured request fails, the summary file shows a **warning** and **existing pending candidates are left untouched** — a transient error never clears them.

Re-running the same day refreshes only **unprocessed** candidates; it never recreates an event you already confirmed or skipped.

### What gets sent

With this feature enabled, the plain-text instructions sent to ChatGPT additionally include:

- Household member names
- The **display names** of selectable calendars
- Local EventKit IDs

so the model can suggest routing. **The actual contents of your Google Calendar are never read or uploaded.**

The state diagram is in [architecture](architecture.en.md#calendar-candidate-state-machine).

---

## Related documents

- [Architecture → cloud summary path](architecture.en.md#cloud-summary-path) — the full sequence diagram
- [Configuration → summary](configuration.en.md#summary) — every summary parameter
- [Privacy and trust boundaries](privacy.en.md) — the full threat model
- [Use-case guide](use-cases.en.md) — prompt templates for other scenarios
- [Troubleshooting](troubleshooting.en.md#the-summary-never-ran) — summary-related problems
