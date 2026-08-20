# Architecture

**English** · [繁體中文](architecture.md) · [Back to docs index](README.en.md)

FamilyRecorder deliberately separates the **always-on local path** from the **scheduled cloud path**. This document explains how the two are composed, how data flows, and exactly where the trust boundary sits.

---

## Contents

- [Design principles](#design-principles)
- [Layered overview](#layered-overview)
- [Module map](#module-map)
- [Capture path: the life of a 30-second chunk](#capture-path-the-life-of-a-30-second-chunk)
- [Recognition path: Whisper and text filtering](#recognition-path-whisper-and-text-filtering)
- [Per-segment enrichment: speaker and direction](#per-segment-enrichment-speaker-and-direction)
- [Cloud summary path](#cloud-summary-path)
- [Calendar candidate state machine](#calendar-candidate-state-machine)
- [Process topology](#process-topology)
- [Menu bar control path](#menu-bar-control-path)
- [Uninstall boundary](#uninstall-boundary)
- [Trust boundary summary](#trust-boundary-summary)
- [Explicit non-goals](#explicit-non-goals)

---

## Design principles

| Principle | How it is enforced |
|---|---|
| **Boundaries must be testable, not promised in a prompt** | The summary path opens only `transcripts/YYYY-MM-DD.md`; there is no audio-decoding or upload implementation anywhere in that code path |
| **Silence should not produce data** | When the fused gate judges a chunk silent, no WAV is written and Whisper is never invoked — only low-volume telemetry remains |
| **No single sensor is authoritative** | Software VAD and hardware Speech Energy rescue and veto each other, but neither decides alone |
| **Approximate results must read as approximate** | Output always says 可能 (*likely*), 可能多人 (*possibly multiple*), or 不確定 (*uncertain*) — never a confirmed identity |
| **Degrade, never abort** | If USB telemetry is unreadable, capture and transcription continue and direction is marked unavailable |
| **Removal must be complete and recoverable** | Uninstall moves everything to the Trash rather than deleting, so the user can still undo it |

---

## Layered overview

```mermaid
flowchart TB
    subgraph L0["① Hardware · XVF3800 / XMOS"]
        direction LR
        UAC["UAC audio interface<br/>left channel = processed beam"]
        CTRL["USB vendor control<br/>DOA_VALUE · AEC_SPENERGY_VALUES"]
    end

    subgraph L1["② Capture · audio.py · devices.py · direction.py"]
        direction LR
        REC["AudioRecorder<br/>one open PortAudio stream<br/>fixed-duration mono PCM16"]
        SAMP["DirectionSampler<br/>one row per 0.25s, shared offset"]
    end

    subgraph L2["③ Decision · metrics.py · hallucination.py · listener.py"]
        direction LR
        ANA["analyze_audio<br/>RMS · VAD · low-freq ratio · tonality"]
        GATE["decide_capture_gate<br/>software / hardware fusion"]
    end

    subgraph L3["④ Recognition · transcriber.py"]
        WSP["WhisperCppTranscriber<br/>whisper-cli subprocess · full JSON"]
        TFIL["transcription_filter_decision<br/>token confidence · repetition · similarity"]
    end

    subgraph L4["⑤ Enrichment · speakers.py · direction.py"]
        direction LR
        SPK["identify_speaker<br/>spectral · pitch · timing features"]
        DIR["direction_for_interval<br/>circular clustering · front rotation"]
    end

    subgraph L5["⑥ Storage · storage.py"]
        direction LR
        MDF["Markdown transcript<br/>one file per date"]
        SQL[("listener.sqlite3<br/>7 tables")]
    end

    subgraph L6["⑦ Summary · summary.py"]
        RUN["DailySummaryRunner<br/>reads transcripts/ only"]
        CDX["codex exec<br/>ephemeral · read-only sandbox"]
    end

    subgraph L7["⑧ Presentation · Swift menu bar app"]
        MENU["FamilyRecorder.app<br/>status · pause · settings · EventKit"]
    end

    UAC --> REC
    CTRL --> SAMP
    REC --> ANA --> GATE
    SAMP --> GATE
    GATE -->|"keep"| WSP --> TFIL
    GATE -->|"discard"| SQL
    TFIL -->|"rejected"| SQL
    TFIL -->|"accepted"| SPK
    SAMP --> DIR
    REC --> SPK
    SPK --> MDF
    DIR --> MDF
    SPK --> SQL
    DIR --> SQL
    MDF --> RUN --> CDX --> SQL
    MENU -.->|"CLI invocation"| GATE
    MENU -.->|"CLI invocation"| RUN
    SQL -.->|"pending candidates"| MENU

    classDef hw fill:#fff3e0,stroke:#e65100,color:#3e2723
    classDef local fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef cloud fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef ui fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
    class L0 hw
    class L1,L2,L3,L4,L5 local
    class L6 cloud
    class L7 ui
```

Layers ① through ⑤ are entirely offline. Layer ⑥ is the only one that reaches the network, and it sends plain text only.

---

## Module map

`src/family_recorder/` contains 18 modules, roughly 5,200 lines. Dependencies are deliberately one-directional: lower modules never import higher ones.

```mermaid
flowchart LR
    CFG["config.py<br/>YAML load and validation"]
    DEV["devices.py"]
    AUD["audio.py"]
    MET["metrics.py"]
    TRN["transcriber.py"]
    DIR["direction.py"]
    SPK["speakers.py"]
    HAL["hallucination.py"]
    CTL["control.py"]
    STO["storage.py"]
    LIS["listener.py"]
    SUM["summary.py"]
    PLC["placement.py"]
    MDL["model_manager.py"]
    CED["config_editor.py"]
    CLI["cli.py<br/>single entry point"]

    CFG --> DEV & AUD & MET & TRN & DIR & SPK & HAL & STO & SUM & PLC & MDL
    DEV --> AUD
    AUD --> STO & PLC & LIS
    MET --> HAL & STO & PLC & LIS
    TRN --> HAL & PLC & LIS
    DIR --> HAL & STO & LIS
    SPK --> STO & LIS
    HAL --> LIS
    CTL --> LIS & CLI
    STO --> SUM & LIS & CLI
    LIS --> CLI
    SUM --> CLI
    PLC --> CLI
    MDL --> CLI
    CED --> CLI

    classDef base fill:#eceff1,stroke:#546e7a,color:#263238
    classDef mid fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef top fill:#fff3e0,stroke:#e65100,color:#3e2723
    class CFG,DEV,AUD,MET base
    class TRN,DIR,SPK,HAL,CTL,STO mid
    class LIS,SUM,PLC,MDL,CED,CLI top
```

| Module | Lines | Responsibility |
|---|---:|---|
| `config.py` | 432 | YAML schema, defaults, path expansion; every other module depends on it |
| `devices.py` | 117 | Enumerate macOS input devices and score-select XVF3800 / XMOS / USB arrays |
| `audio.py` | 155 | `AudioRecorder`, downmix, resampling, WAV read/write, PCM slicing |
| `metrics.py` | 148 | RMS, SNR, WebRTC VAD speech ratio, low-frequency ratio, tonal concentration |
| `transcriber.py` | 229 | `whisper-cli` subprocess, JSON segment and token parsing, common-term correction |
| `direction.py` | 567 | XVF3800 USB control, DoA and four-beam Speech Energy, circular clustering |
| `speakers.py` | 350 | Feature extraction, profile storage, approximate speaker identification |
| `hallucination.py` | 162 | Acoustic-layer and text-layer rejection logic, adaptive noise floor |
| `control.py` | 84 | Atomic read/write of the `control.json` pause state |
| `storage.py` | 678 | SQLite schema and migrations, Markdown append, retention |
| `listener.py` | 479 | The resident loop: capture → gate → transcribe → enrich → store |
| `summary.py` | 515 | Daily summary, time/speaker/direction contracts, calendar extraction |
| `placement.py` | 197 | A/B/C placement test and CER report |
| `model_manager.py` | 217 | Whisper model catalog, download, resume, GGML validation |
| `config_editor.py` | 83 | Targeted YAML edits that preserve unrelated comments |
| `cli.py` | 777 | Every subcommand; the menu bar app touches the system only through this layer |

---

## Capture path: the life of a 30-second chunk

`AudioRecorder` selects an input and holds exactly **one** PortAudio stream open, emitting fixed-duration mono PCM16. With the default `audio.channels: 1`, CoreAudio/PortAudio captures the first (left) UAC channel.

Stereo downmix is treated as **ambiguous**: the right channel can carry ASR/AEC-residual data whose processing purpose differs from the left, and averaging the two destroys the beamformed signal. `diagnose-beamforming` reads `AUDIO_MGR_OP_L/R` without modifying the device and verifies that the left channel is category `6` processed beamformed data, or category `8`'s copy of the processed auto-selected beam.

### Gate decision order

```mermaid
flowchart TB
    START["30-second chunk captured"] --> ANA["analyze_audio<br/>RMS · SNR · speech_ratio<br/>low-freq ratio · tonality"]
    ANA --> SWQ{"Software VAD passes?"}

    SWQ -->|"yes"| HWSIL{"hardware silence<br/>+ software weak<br/>+ SNR weak"}
    HWSIL -->|"all three"| R1["discard<br/>hardware_silence"]
    HWSIL -->|"no"| TONAL{"tonal / low-freq noise<br/>+ not hardware speech<br/>+ both weak"}
    TONAL -->|"yes"| R2["discard<br/>tonal_noise"]
    TONAL -->|"no"| NOISE{"near noise floor<br/>+ not hardware speech<br/>+ both weak"}
    NOISE -->|"yes"| R3["discard<br/>adaptive_noise_floor"]
    NOISE -->|"no"| K1["keep<br/>software_vad"]

    SWQ -->|"no"| HWQ{"Can hardware<br/>Speech Energy rescue it?"}
    HWQ -->|"yes"| K2["keep<br/>xvf3800_speech_energy"]
    HWQ -->|"no"| UNAVL{"telemetry unreadable?"}
    UNAVL -->|"yes"| R4["discard<br/>speech_energy_unavailable"]
    UNAVL -->|"no"| R5["discard<br/>silence"]

    K1 --> WAV["write WAV<br/>send to Whisper"]
    K2 --> WAV
    R1 & R2 & R3 & R4 & R5 --> TEL["no WAV created<br/>still written to captures<br/>and acoustic_samples"]

    classDef keep fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef drop fill:#ffebee,stroke:#c62828,color:#b71c1c
    classDef q fill:#fff8e1,stroke:#f9a825,color:#e65100
    class K1,K2,WAV keep
    class R1,R2,R3,R4,R5,TEL drop
    class SWQ,HWSIL,TONAL,NOISE,HWQ,UNAVL q
```

The discard labels above are abbreviated. The full `captures.gate_reason` values are `hallucination_filter:hardware_silence`, `hallucination_filter:tonal_noise`, `hallucination_filter:adaptive_noise_floor`, `software_vad; speech_energy_unavailable`, and `silence` — see [data and SQLite](data-model.en.md#possible-gate_reason-values).

Three things matter here:

1. **Hardware rescue can only push toward keeping, once**, and the chunk must still clear `speech_energy_min_rms_dbfs`, so a single non-zero hardware sample cannot push extremely faint noise into Whisper.
2. **Hardware veto requires three conditions simultaneously** (hardware silence, weak software evidence, weak SNR), so one sensor treated as ground truth cannot silently drop real speech.
3. **When USB control is temporarily unreadable**, the adaptive noise floor plus tonal/low-frequency evidence takes over and capture is never aborted.

Every completed chunk is written to `captures`, including those judged silent with no WAV; the full time series goes to `acoustic_samples`. Telemetry failures never abort UAC recording or local transcription.

---

## Recognition path: Whisper and text filtering

`WhisperCppTranscriber` invokes `whisper-cli` as a subprocess and reads the **full JSON**: segment timestamps and token probabilities are both retained, not just plain text. Decoder no-speech and log-probability thresholds are passed down to whisper.cpp; a second text-level filter runs on the result.

```mermaid
flowchart TB
    IN["whisper-cli JSON<br/>segments + tokens"] --> EMPTY{"Text empty?"}
    EMPTY -->|"yes"| ST_EMPTY["status = empty<br/>no Markdown written"]
    EMPTY -->|"no"| NS{"no-speech probability ≥ 0.60"}
    NS -->|"yes"| F1["reject<br/>whisper_no_speech"]
    NS -->|"no"| LP{"avg_logprob &lt; -0.80"}
    LP -->|"yes"| F2["reject<br/>whisper_low_logprob"]
    LP -->|"no"| TOK{"low-confidence tokens &gt; 0.15"}
    TOK -->|"yes"| F3["reject<br/>whisper_low_token_confidence"]
    TOK -->|"no"| CR{"compression ratio &gt; 2.40"}
    CR -->|"yes"| F4["reject<br/>whisper_repetitive_text"]
    CR -->|"no"| SHORT{"too short?<br/>e.g. an interjection"}
    SHORT -->|"yes"| OK["accept"]
    SHORT -->|"no"| REP{"similar long sentence<br/>within 300s?"}
    REP -->|"yes"| F5["reject<br/>repeated_across_chunks"]
    REP -->|"no"| OK

    OK --> WRITE["append to the day's Markdown<br/>status = transcribed"]
    F1 & F2 & F3 & F4 & F5 --> AUD["written to transcription_audits only<br/>never enters Markdown or the cloud summary"]

    classDef keep fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef drop fill:#ffebee,stroke:#c62828,color:#b71c1c
    classDef q fill:#fff8e1,stroke:#f9a825,color:#e65100
    class OK,WRITE keep
    class F1,F2,F3,F4,F5,AUD,ST_EMPTY drop
    class EMPTY,NS,LP,TOK,CR,SHORT,REP q
```

The values shown are the *balanced* preset. They can be changed through the menu bar's three presets or its advanced editor — see the [configuration reference](configuration.en.md#hallucination_filter).

**No rule blacklists any particular sentence.** Hallucinated text changes with the model and the prompt, so a blacklist goes stale quickly. Rejection is therefore based on statistical properties — confidence, repetitiveness, cross-chunk similarity — rather than literal matching.

Rejected candidate text, the decision, the reason, average log probability, low-probability token ratio, compression ratio, and similarity count all go to `transcription_audits`, so "why did that sentence not appear?" is answerable after the fact. A **failed** transcription is indexed as `failed` and keeps its WAV for diagnosis, with retention independent of transcript retention.

---

## Per-segment enrichment: speaker and direction

Whisper returns timestamps at **second-level granularity**, not one label per 30 seconds. Enrichment therefore happens per segment:

```mermaid
sequenceDiagram
    autonumber
    participant L as listener.py
    participant W as WhisperCppTranscriber
    participant S as speakers.py
    participant D as direction.py
    participant DB as storage.py

    L->>W: submit the 30-second WAV
    W-->>L: segments[] with start/end seconds and tokens
    loop for each Whisper segment
        L->>L: slice_pcm16 for that segment's PCM
        L->>S: extract_feature_vector — spectral / pitch / timing
        S->>S: cosine comparison against enrolled profiles
        S-->>L: recognized / mixed / uncertain + similarity
        L->>D: direction_for_interval over the same interval
        D->>D: circular clustering, then rotate by front_angle_degrees
        D-->>L: primary angle · label · stability · multiple?
        L->>DB: one segments row + several direction_samples rows
        L->>DB: append the Markdown segment heading
    end
```

The resulting heading looks like this:

```markdown
### 19:40:07–19:40:12 — 可能：家人二（87%） — 方向：左側 92°；穩定度 80%
```

(*likely: family member 2 (87%) — direction: left 92°; stability 80%*)

### Two pieces of evidence that never substitute for each other

| | Voice timbre | Sound direction |
|---|---|---|
| **Source** | Local acoustic feature-vector comparison | XVF3800 firmware DoA |
| **Can answer** | Whether this audio **resembles** an enrolled member | What **angle** the source sits at relative to the mic |
| **Cannot answer** | Verified identity, forensic word-level voiceprints | Who it is, distance, room coordinates |
| **On failure** | `uncertain` or `mixed` | `unavailable` or `multiple` |

A stable direction can **corroborate** a voice label and reveal a change of speaker within one 30-second chunk, but it cannot map a location to a person. Two significant direction clusters are retained as `multiple` rather than collapsed onto the primary voice label. **A segment with no timbre-derived name is never assigned to a household member on direction alone.**

Enrollment audio exists only in memory and is discarded once features are computed — no WAV is ever created. Profiles are stored mode `0600` under `speaker-profiles/`. See [Speakers and direction](speakers.en.md).

---

## Cloud summary path

`DailySummaryRunner` accepts a calendar date and opens **only** the corresponding Markdown file under `transcripts/`.

```mermaid
sequenceDiagram
    autonumber
    participant LA as launchd<br/>com.familyrecorder.summary
    participant R as DailySummaryRunner
    participant FS as transcripts/
    participant CX as codex exec
    participant CT as ChatGPT account
    participant DB as listener.sqlite3
    participant EK as EventKit

    LA->>R: fires at the scheduled time · yesterday by default
    R->>FS: read YYYY-MM-DD.md only
    FS-->>R: transcript text
    R->>R: append time / speaker / direction output contracts
    alt longer than summary.max_input_chars
        R->>R: split only between complete segment headings
        loop each part
            R->>CX: pipe the part over stdin + the same contracts
            CX->>CT: ephemeral · read-only sandbox
            CT-->>CX: partial summary
        end
        R->>CX: final merge request + the same contracts
    else within the limit
        R->>CX: pipe the whole transcript over stdin + contracts
    end
    CX-->>R: Markdown summary
    R->>FS: write summaries/YYYY-MM-DD.md
    R->>DB: upsert one summaries row

    opt calendar.enabled
        R->>CX: second request · --output-schema strict JSON
        CX-->>R: candidate event array
        R->>R: normalize · reject unresolvable dates
        R->>DB: insert calendar_candidates as pending
        DB-->>EK: per-event confirmation, or automatic after one opt-in
    end
```

### The time contract

Transcript headings carry local chunk ranges such as `19:40:00–19:40:30`. The code appends a time-output contract to **every** request, independently of the user-configurable `summary.prompt`. It requires:

- Minute-level timestamps, prefixed with 約 (*approximately*)
- Events ordered chronologically
- An explicit 時間不明 (*time unknown*) marker when a fact cannot be traced to a source segment
- A **prohibition** on substituting the summary's own generation time for source time

Both the partial requests and the final merge carry the same contract, so chunking cannot silently discard chronology. Speaker and direction contracts work the same way: speaker and task owner must stay distinct, direction alone can never supply a missing name, and unlabeled or mixed segments cannot be assigned to a person.

### Why "text only" is testable

| Protection | Mechanism |
|---|---|
| No audio read | The `summary` code path contains no audio decoding or upload implementation |
| No voice features read | `audio/` and `speaker-profiles/` are never opened |
| Not exposed in the process list | The transcript is piped over stdin, never placed in process arguments |
| No credential file read | Only the official `codex login status` is executed; the Codex token file is never opened |
| No transcript-driven injection | The prompt states that transcript content is untrusted and forbids tool use |
| No residue | Every invocation is `--ephemeral`, `--sandbox read-only`, in an empty temporary working directory, ignoring user config and project rules |

---

## Calendar candidate state machine

Calendar extraction is a **separate second request** issued only after the human-readable summary succeeds. It uses `--output-schema` with a strict JSON Schema and receives only summary and transcript text. **That request never creates an external event.**

```mermaid
stateDiagram-v2
    direction LR
    [*] --> pending: Codex returned a valid candidate<br/>written to SQLite
    pending --> created: user confirmed one by one<br/>or auto_create was opted into once
    pending --> dismissed: user skipped it
    pending --> failed: EventKit write failed
    failed --> pending: retried on the next summary run
    created --> [*]
    dismissed --> [*]

    note right of pending
        Re-running the same day only
        refreshes unprocessed candidates
    end note
    note right of created
        The EventKit note carries the
        SQLite candidate ID, so an
        interrupted update deduplicates
    end note
```

- A date with no time becomes an all-day candidate; a date that cannot be resolved is rejected rather than guessed.
- The default path requires **per-event confirmation**. `auto_create` requires one explicit opt-in, after which the continuously running menu app notices `pending` rows and writes them through EventKit.
- Every EventKit note carries the SQLite candidate ID, so an interrupted status update can be deduplicated before retry.
- A failed or malformed extraction leaves **existing pending candidates untouched** and adds a visible warning to the Markdown summary.

---

## Process topology

```mermaid
flowchart TB
    subgraph GUI["Aqua login session"]
        APP["/Applications/FamilyRecorder.app<br/>native AppKit status item"]
    end

    subgraph AGENTS["Per-user LaunchAgents · no root daemons"]
        A1["com.familyrecorder.listener<br/>RunAtLoad + KeepAlive"]
        A2["com.familyrecorder.summary<br/>StartCalendarInterval"]
        A3["com.familyrecorder.menubar<br/>starts at login"]
    end

    subgraph RT["~/Library/Application Support/FamilyRecorder"]
        VENV["venv/bin/family-recorder<br/>Python CLI"]
        WC["whisper.cpp/ and ggml-*.bin"]
        UNI["uninstaller app"]
    end

    subgraph DATA["~/xvf3800-listener-data"]
        D1["audio/ · transcripts/ · summaries/"]
        D2["speaker-profiles/ · logs/ · control.json"]
        D3[("listener.sqlite3")]
    end

    A1 -->|"listener service"| APP
    A2 -->|"summary service"| APP
    A3 --> APP
    APP -->|"holds mic and calendar grants as the app identity"| VENV
    VENV --> WC
    VENV --> DATA
    APP -->|"opens"| UNI
    UNI -.->|"stops all three agents, then moves to Trash"| RT
    UNI -.->|"full mode only"| DATA

    classDef gui fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
    classDef agent fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef rt fill:#eceff1,stroke:#546e7a,color:#263238
    classDef data fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    class GUI gui
    class AGENTS agent
    class RT rt
    class DATA data
```

All three jobs are **per-user LaunchAgents, not root daemons**. No API key or Codex token is placed in launchd environment variables; the summary job provides only `HOME` so the official CLI can locate its own saved login.

All three are associated with the **same app** in `/Applications`, avoiding the Spotlight/TCC identity-cache inconsistency that hidden or user-level paths cause. macOS therefore shows a single `FamilyRecorder.app` under Privacy & Security → Microphone, rather than `python3.12`.

---

## Menu bar control path

The Swift menu bar app **never manipulates system state directly**. It invokes the installed `family-recorder` CLI for status, pause/resume, targeted YAML edits, summaries, diagnostics, and intentional speaker enrollment.

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant M as Menu bar app
    participant C as family-recorder CLI
    participant J as control.json
    participant L as listener process

    U->>M: click "pause 15 minutes"
    M->>C: family-recorder pause --minutes 15
    C->>J: atomically persist pause state and expiry
    L->>J: checked once per second
    L->>L: microphone stream closes within about one second
    Note over L: the in-flight chunk is discarded, never saved
    J-->>L: resumes automatically at expiry

    U->>M: click "record a voice sample"
    M->>C: check microphone authorization first
    alt not authorized
        C-->>M: refuse and offer the Settings link
        M-->>U: no doomed recording is started
    else authorized
        M->>C: enroll-speaker --name ... --seconds 15
        C->>J: pause, initiated by the menu
        C->>C: PCM stays in memory → features → 0600 JSON
        C->>J: resume only because the menu initiated the pause
    end
```

- Pause state lives in `data_dir/control.json`, **not just UI memory**, so restarting the menu bar app never accidentally resumes recording.
- Whisper model choices are discovered from **already-downloaded** `ggml-*.bin` files, not a hardcoded list.
- Targeted config edits (`config_editor.py`) preserve unrelated YAML comments and values.
- Changing hallucination thresholds or the local model restarts the listener; the Codex summary model is read fresh on every summary run and needs no restart.

---

## Uninstall boundary

The menu bar does **not** delete its own runtime inline. It opens a **separately signed native uninstaller**, which can therefore stop all three LaunchAgents before moving the running menu app, Python environment, whisper.cpp checkout, and models.

```mermaid
flowchart TB
    START["user chooses uninstall"] --> MODE{"pick a mode"}
    MODE -->|"program only"| M1["stop all three LaunchAgents<br/>move runtime · app · models<br/>keep data_dir and config.yaml"]
    MODE -->|"complete removal"| M2["as above, plus the data roots"]
    M2 --> MARK{"Does the data directory carry<br/>the .familyrecorder-data marker?"}
    MARK -->|"yes"| M3["move the whole data root"]
    MARK -->|"no · older or custom shared path"| M4["move only known FamilyRecorder<br/>children and the database<br/>unrelated files stay in place"]
    M1 & M3 & M4 --> TRASH["everything goes to one<br/>timestamped Trash folder"]
    TRASH --> REC["recoverable until the user empties Trash"]

    SAFE["Safety check: refuses / , the user home<br/>directory, Trash, and the LaunchAgents<br/>directory as removal targets"] -.-> MARK
    OUT["Explicitly outside the boundary:<br/>ChatGPT/Codex login · Homebrew packages<br/>Python · Git · CMake · PortAudio<br/>the GitHub repo · downloaded DMGs"] -.-> TRASH

    classDef safe fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef warn fill:#fff8e1,stroke:#f9a825,color:#e65100
    class SAFE,REC,M4 safe
    class OUT warn
```

---

## Trust boundary summary

```mermaid
flowchart TB
    DEV["🎙️ Device: raw four-microphone signal"]

    subgraph MAC["🔒 This Mac"]
        NEVER["Never leaves:<br/>WAV audio · voice feature vectors<br/>DoA · Speech Energy<br/>rejection audits · SQLite · logs"]
        TXT["transcript text"]
    end

    NETW["☁️ Network: your own ChatGPT account"]

    DEV ==> NEVER ==> TXT
    TXT -->|"once a day · text only"| NETW

    classDef never fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef leaves fill:#fff8e1,stroke:#f9a825,color:#e65100
    classDef outside fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef dev fill:#fff3e0,stroke:#e65100,color:#3e2723
    class MAC,NEVER never
    class TXT leaves
    class NETW outside
    class DEV dev
```

The four `-.-x` edges mean **never leaves this Mac**. The only thing that crosses the boundary is transcript text, once per day. Full threat model in [Privacy and trust boundaries](privacy.en.md).

---

## Explicit non-goals

These are not "not yet built" — they are **deliberately excluded**:

- ❌ Biometric-grade speaker identification, authentication, or word-level diarization
- ❌ Treating DoA as identity, distance, room coordinates, or proof that one person spoke an entire segment
- ❌ Covert recording
- ❌ Live cloud transcription
- ❌ Uploading or remotely backing up raw audio
- ❌ Acting on inferred tasks or reminders
- ❌ A web dashboard

---

## Further reading

- [Data and SQLite](data-model.en.md) — every table and column
- [Privacy and trust boundaries](privacy.en.md) — threat model and consent
- [Configuration reference](configuration.en.md) — the parameters behind every decision point above
- [Use-case guide](use-cases.en.md) — how the same architecture becomes a different service
