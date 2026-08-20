# 系統架構

[English](architecture.en.md) · **繁體中文** · [返回文件索引](README.md)

FamilyRecorder 刻意把**常駐的本機路徑**與**排程的雲端路徑**分開。這份文件說明兩者如何組成、資料怎麼流動，以及信任邊界落在哪裡。

---

## 目錄

- [設計原則](#設計原則)
- [分層總覽](#分層總覽)
- [模組地圖](#模組地圖)
- [收音路徑：30 秒 chunk 的一生](#收音路徑30-秒-chunk-的一生)
- [辨識路徑：Whisper 與文字防幻覺](#辨識路徑whisper-與文字防幻覺)
- [逐段標註：人別與方向](#逐段標註人別與方向)
- [雲端摘要路徑](#雲端摘要路徑)
- [行事曆候選事件狀態機](#行事曆候選事件狀態機)
- [程序拓撲](#程序拓撲)
- [選單列控制路徑](#選單列控制路徑)
- [解除安裝邊界](#解除安裝邊界)
- [信任邊界總結](#信任邊界總結)
- [明確非目標](#明確非目標)

---

## 設計原則

| 原則 | 具體做法 |
|---|---|
| **邊界要能被測試，而不是靠 prompt 承諾** | 摘要程式只開啟 `transcripts/YYYY-MM-DD.md`，程式碼中沒有任何音訊解碼或上傳實作 |
| **安靜不該產生資料** | 融合閘門判定為安靜時不建立 WAV、不呼叫 Whisper；只留低容量遙測 |
| **兩個感測器不能互相取代** | software VAD 與硬體 Speech Energy 互為救援與否決，但單一感測器不能獨斷 |
| **近似結果要說成近似** | 一律使用「可能說話者」「可能多人」「不確定」，不輸出確定身分 |
| **失敗要降級，不要中止** | USB 遙測讀不到時，錄音與轉錄繼續，方向標成「無法讀取」 |
| **可以完整移除** | 解除安裝把所有內容移到垃圾桶而不是直接刪除，使用者仍可復原 |

---

## 分層總覽

```mermaid
flowchart TB
    subgraph L0["① 硬體層 · XVF3800 / XMOS"]
        direction LR
        UAC["UAC 音訊介面<br/>左聲道 = processed beam"]
        CTRL["USB vendor control 介面<br/>DOA_VALUE · AEC_SPENERGY_VALUES"]
    end

    subgraph L1["② 擷取層 · audio.py · devices.py · direction.py"]
        direction LR
        REC["AudioRecorder<br/>單一 PortAudio stream<br/>固定長度 mono PCM16"]
        SAMP["DirectionSampler<br/>每 0.25 秒一列共同 offset"]
    end

    subgraph L2["③ 決策層 · metrics.py · hallucination.py · listener.py"]
        direction LR
        ANA["analyze_audio<br/>RMS · VAD · 低頻比 · 窄頻集中度"]
        GATE["decide_capture_gate<br/>software / hardware 融合"]
    end

    subgraph L3["④ 辨識層 · transcriber.py"]
        WSP["WhisperCppTranscriber<br/>whisper-cli 子程序 · 完整 JSON"]
        TFIL["transcription_filter_decision<br/>token 信心 · 重複 · 跨 chunk 相似"]
    end

    subgraph L4["⑤ 標註層 · speakers.py · direction.py"]
        direction LR
        SPK["identify_speaker<br/>頻譜 · 音高 · 時長特徵"]
        DIR["direction_for_interval<br/>環狀分群 · 正前方旋轉"]
    end

    subgraph L5["⑥ 儲存層 · storage.py"]
        direction LR
        MDF["Markdown 逐字稿<br/>依日期分檔"]
        SQL[("listener.sqlite3<br/>7 張表")]
    end

    subgraph L6["⑦ 摘要層 · summary.py"]
        RUN["DailySummaryRunner<br/>只讀取 transcripts/"]
        CDX["codex exec<br/>ephemeral · read-only sandbox"]
    end

    subgraph L7["⑧ 呈現層 · Swift 選單列 App"]
        MENU["FamilyRecorder.app<br/>狀態 · 暫停 · 設定 · EventKit"]
    end

    UAC --> REC
    CTRL --> SAMP
    REC --> ANA --> GATE
    SAMP --> GATE
    GATE -->|"保留"| WSP --> TFIL
    GATE -->|"丟棄"| SQL
    TFIL -->|"攔截"| SQL
    TFIL -->|"通過"| SPK
    SAMP --> DIR
    REC --> SPK
    SPK --> MDF
    DIR --> MDF
    SPK --> SQL
    DIR --> SQL
    MDF --> RUN --> CDX --> SQL
    MENU -.->|"CLI 呼叫"| GATE
    MENU -.->|"CLI 呼叫"| RUN
    SQL -.->|"待確認候選"| MENU

    classDef hw fill:#fff3e0,stroke:#e65100,color:#3e2723
    classDef local fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef cloud fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef ui fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
    class L0 hw
    class L1,L2,L3,L4,L5 local
    class L6 cloud
    class L7 ui
```

①–⑤ 完全離線；⑥ 是唯一會對外連線的層，且只送純文字。

---

## 模組地圖

`src/family_recorder/` 共 18 個模組，約 5,200 行。相依關係刻意保持單向：底層模組不認識上層。

```mermaid
flowchart LR
    CFG["config.py<br/>YAML 載入與驗證"]
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
    CLI["cli.py<br/>唯一進入點"]

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

| 模組 | 行數 | 職責 |
|---|---:|---|
| `config.py` | 432 | YAML schema、預設值、路徑展開；所有其他模組的相依起點 |
| `devices.py` | 117 | 列舉 macOS 輸入裝置並評分挑選 XVF3800／XMOS／USB 陣列 |
| `audio.py` | 155 | `AudioRecorder`、downmix、重新取樣、WAV 讀寫、PCM 切片 |
| `metrics.py` | 148 | RMS、SNR、WebRTC VAD speech ratio、低頻比、窄頻集中度 |
| `transcriber.py` | 229 | `whisper-cli` 子程序呼叫、JSON 段落與 token 解析、常用字詞校正 |
| `direction.py` | 567 | XVF3800 USB control、DoA 與四束 Speech Energy、環狀分群 |
| `speakers.py` | 350 | 特徵抽取、profile 儲存、近似人別判定 |
| `hallucination.py` | 162 | 聲學層與文字層的攔截判斷、自適應噪音基線 |
| `control.py` | 84 | `control.json` 暫停狀態的原子讀寫 |
| `storage.py` | 678 | SQLite schema／migration、Markdown 附加、retention |
| `listener.py` | 479 | 常駐主迴圈：擷取→閘門→轉錄→標註→儲存 |
| `summary.py` | 515 | 每日摘要、時間／人別／方向契約、行事曆候選擷取 |
| `placement.py` | 197 | A/B/C 擺位測試與 CER 報告 |
| `model_manager.py` | 217 | Whisper 模型清單、下載、續傳、GGML 驗證 |
| `config_editor.py` | 83 | 保留註解的目標式 YAML 編輯 |
| `cli.py` | 777 | 全部子指令；選單列 App 只透過這一層操作系統 |

---

## 收音路徑：30 秒 chunk 的一生

`AudioRecorder` 選定輸入後只開啟**一條** PortAudio stream，持續產出固定長度的 mono PCM16。預設 `audio.channels: 1`，CoreAudio／PortAudio 因此擷取第一個（左）UAC 聲道。

立體聲 downmix 被視為**語意不明**：右聲道可能承載 ASR/AEC residual，與左聲道的處理目的不同，平均混合會破壞 beamformed 訊號。`diagnose-beamforming` 在不修改裝置的前提下讀回 `AUDIO_MGR_OP_L/R`，確認左聲道是 category `6` 的 processed beamformed，或 category `8` 對 processed auto-selected beam 的複製。

### 融合閘門的判定順序

```mermaid
flowchart TB
    START["30 秒 chunk 擷取完成"] --> ANA["analyze_audio<br/>RMS · SNR · speech_ratio<br/>低頻比 · 窄頻集中度"]
    ANA --> SWQ{"software VAD 通過？<br/>speech_ratio ≥ min_speech_ratio<br/>且 RMS ≥ min_rms_dbfs"}

    SWQ -->|"是"| HWSIL{"硬體靜音守門<br/>Speech Energy ≈ 0<br/>且 software 證據弱<br/>且 SNR 弱"}
    HWSIL -->|"三者皆成立"| R1["丟棄<br/>hallucination_filter:hardware_silence"]
    HWSIL -->|"否"| TONAL{"低頻／窄頻固定音<br/>且非硬體語音<br/>且 software 與 SNR 皆弱"}
    TONAL -->|"是"| R2["丟棄<br/>hallucination_filter:tonal_noise"]
    TONAL -->|"否"| NOISE{"接近自適應噪音基線<br/>且非硬體語音<br/>且 software 與 SNR 皆弱"}
    NOISE -->|"是"| R3["丟棄<br/>hallucination_filter:adaptive_noise_floor"]
    NOISE -->|"否"| K1["保留<br/>gate_reason = software_vad"]

    SWQ -->|"否"| HWQ{"硬體救援？<br/>direction 與 speech_energy 啟用<br/>status = speech<br/>speech_ratio ≥ min_ratio<br/>且 RMS ≥ speech_energy_min_rms_dbfs"}
    HWQ -->|"是"| K2["保留<br/>gate_reason = xvf3800_speech_energy"]
    HWQ -->|"否"| UNAVL{"Speech Energy 讀不到？"}
    UNAVL -->|"是"| R4["丟棄<br/>software_vad; speech_energy_unavailable"]
    UNAVL -->|"否"| R5["丟棄<br/>gate_reason = silence"]

    K1 --> WAV["寫入 WAV<br/>送進 Whisper"]
    K2 --> WAV
    R1 & R2 & R3 & R4 & R5 --> TEL["不建立 WAV<br/>仍寫入 captures 與 acoustic_samples"]

    classDef keep fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef drop fill:#ffebee,stroke:#c62828,color:#b71c1c
    classDef q fill:#fff8e1,stroke:#f9a825,color:#e65100
    class K1,K2,WAV keep
    class R1,R2,R3,R4,R5,TEL drop
    class SWQ,HWSIL,TONAL,NOISE,HWQ,UNAVL q
```

三個重點：

1. **硬體救援只能往「保留」的方向作用一次**，且仍必須通過 `speech_energy_min_rms_dbfs`，避免單一硬體非零值把極低音量雜訊送進 Whisper。
2. **硬體否決需要三個條件同時成立**（硬體靜音、software 證據弱、SNR 弱），避免把單一感測器當成絕對真相而漏字。
3. **USB control 暫時讀不到時**，自適應噪音基線與低頻／窄頻特徵接手，錄音不中斷。

每一個完成擷取的 chunk 都會寫入 `captures`，包含被判為安靜、沒有 WAV 的那些；完整時間序列寫入 `acoustic_samples`。遙測失敗永遠不會中止 UAC 錄音或本機轉錄。

---

## 辨識路徑：Whisper 與文字防幻覺

`WhisperCppTranscriber` 以子程序呼叫 `whisper-cli`，讀取**完整 JSON**：段落時間戳與 token 機率都會保留，而不是只取純文字。解碼器的 no-speech／log-probability 門檻直接傳給 whisper.cpp；回傳後再做第二層文字過濾。

```mermaid
flowchart TB
    IN["whisper-cli 回傳 JSON<br/>segments + tokens"] --> EMPTY{"文字為空？"}
    EMPTY -->|"是"| ST_EMPTY["segments.status = empty<br/>audits.decision = empty<br/>不寫 Markdown"]
    EMPTY -->|"否"| NS{"no_speech_probability<br/>≥ 0.60"}
    NS -->|"是"| F1["攔截 · whisper_no_speech"]
    NS -->|"否"| LP{"avg_logprob<br/>&lt; -0.80"}
    LP -->|"是"| F2["攔截 · whisper_low_logprob"]
    LP -->|"否"| TOK{"低可信 token 比例<br/>&gt; 0.15"}
    TOK -->|"是"| F3["攔截 · whisper_low_token_confidence"]
    TOK -->|"否"| CR{"壓縮率<br/>&gt; 2.40"}
    CR -->|"是"| F4["攔截 · whisper_repetitive_text"]
    CR -->|"否"| SHORT{"正規化後長度<br/>&lt; min_repeat_text_chars"}
    SHORT -->|"是 · 例如「好」「嗯」"| OK["接受"]
    SHORT -->|"否"| REP{"300 秒視窗內<br/>相似度 ≥ 0.96 的句子<br/>已出現 ≥ max_repetitions 次"}
    REP -->|"是"| F5["攔截 · repeated_across_chunks"]
    REP -->|"否"| OK

    OK --> WRITE["附加到當日 Markdown<br/>segments.status = transcribed<br/>audits.decision = accepted"]
    F1 & F2 & F3 & F4 & F5 --> AUD["只寫入 transcription_audits<br/>decision = filtered<br/>永不進入 Markdown 或雲端摘要"]

    classDef keep fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef drop fill:#ffebee,stroke:#c62828,color:#b71c1c
    classDef q fill:#fff8e1,stroke:#f9a825,color:#e65100
    class OK,WRITE keep
    class F1,F2,F3,F4,F5,AUD,ST_EMPTY drop
    class EMPTY,NS,LP,TOK,CR,SHORT,REP q
```

門檻數值為「平衡」預設，可由選單列的三段預設或進階編輯器調整，詳見 [設定參考](configuration.md#hallucination_filter)。

**這些規則不封鎖任何特定句子。** 幻覺文字會隨模型與提示改變，黑名單很快就失效；因此攔截依據的是統計特徵（信心、重複度、跨片段相似），而不是字面比對。

被攔截的原始候選文字、決策、原因、平均 log probability、低可信 token 比例、壓縮率與相似次數都寫入 `transcription_audits`，方便事後回查「為什麼這句沒有出現」。轉錄**失敗**的 chunk 索引為 `failed` 並保留 WAV 供排查，其 retention 與逐字稿獨立。

---

## 逐段標註：人別與方向

Whisper 回傳的是**數秒級**的段落時間戳，不是整個 30 秒一個標籤。標註因此在段落層級進行：

```mermaid
sequenceDiagram
    autonumber
    participant L as listener.py
    participant W as WhisperCppTranscriber
    participant S as speakers.py
    participant D as direction.py
    participant DB as storage.py

    L->>W: 送出 30 秒 WAV
    W-->>L: segments[] 含 start/end 秒數與 token
    loop 每一個 Whisper 段落
        L->>L: slice_pcm16 取出該段落的 PCM
        L->>S: extract_feature_vector 頻譜／音高／時長
        S->>S: 與已註冊 profile 做 cosine 比對
        S-->>L: recognized / mixed / uncertain + 相似度
        L->>D: direction_for_interval 取同區間的方向樣本
        D->>D: 環狀分群 → 依 front_angle_degrees 旋轉
        D-->>L: 主要角度 · 標籤 · 穩定度 · 是否多方向
        L->>DB: 寫入 segments 一列 + direction_samples 多列
        L->>DB: 附加 Markdown 段落標題
    end
```

產出的標題格式：

```markdown
### 19:40:07–19:40:12 — 可能：家人二（87%） — 方向：左側 92°；穩定度 80%
```

### 兩份證據，不互相取代

| | 音色人別 | 聲音方向 |
|---|---|---|
| **來源** | 本機聲學特徵向量比對 | XVF3800 韌體的 DoA |
| **能回答** | 這段聲音**像不像**某位已註冊成員 | 聲源相對麥克風在**哪個角度** |
| **不能回答** | 確認身分、逐字聲紋鑑識 | 是誰、距離、房間座標 |
| **失敗時** | `uncertain` 或 `mixed` | `unavailable` 或 `multiple` |

穩定的方向可以**佐證**音色判斷，也能揭露同一個 30 秒內的人員變動；但方向不能把位置對應到人。兩個明顯的方向叢集會保留為 `multiple`，不會被收斂成主要的那個人。**沒有音色姓名的片段，絕不會只靠方向指定某位家人。**

註冊音訊只存在記憶體中，產生特徵後即丟棄，不會建立 WAV；特徵以權限 `0600` 保存在 `speaker-profiles/`。詳見 [家庭成員與方向](speakers.md)。

---

## 雲端摘要路徑

`DailySummaryRunner` 接受一個日曆日期，然後**只**開啟 `transcripts/` 底下對應的那一個 Markdown 檔。

```mermaid
sequenceDiagram
    autonumber
    participant LA as launchd<br/>com.familyrecorder.summary
    participant R as DailySummaryRunner
    participant FS as transcripts/
    participant CX as codex exec
    participant CT as ChatGPT 帳號
    participant DB as listener.sqlite3
    participant EK as EventKit

    LA->>R: 每日排定時間觸發 · 預設整理昨天
    R->>FS: 只讀取 YYYY-MM-DD.md
    FS-->>R: 逐字稿文字
    R->>R: 附加時間／人別／方向輸出契約
    alt 超過 summary.max_input_chars
        R->>R: 依完整「### 時間 — 人別 — 方向」段落切分
        loop 每一段
            R->>CX: stdin 傳入分段文字 + 相同契約
            CX->>CT: ephemeral · read-only sandbox
            CT-->>CX: 分段整理
        end
        R->>CX: 最終整併請求 + 相同契約
    else 未超過
        R->>CX: stdin 傳入完整逐字稿 + 契約
    end
    CX-->>R: Markdown 摘要
    R->>FS: 寫入 summaries/YYYY-MM-DD.md
    R->>DB: upsert summaries 一列

    opt calendar.enabled
        R->>CX: 第二次請求 · --output-schema 嚴格 JSON
        CX-->>R: 候選事件陣列
        R->>R: 正規化 · 無法解析日期者拒絕
        R->>DB: 寫入 calendar_candidates 狀態 pending
        DB-->>EK: 逐筆確認，或一次同意後自動建立
    end
```

### 時間契約

逐字稿標題帶有本地 chunk 區間（例如 `19:40:00–19:40:30`）。程式在**每一次**請求中附加一份時間輸出契約，與使用者可自訂的 `summary.prompt` 無關。它要求：

- 時間只到分鐘，並加上「約」
- 事件依時間先後排列
- 無法對應來源段落者標示「時間不明」
- **禁止**用摘要產生時間頂替來源時間

分段與最終整併都會再帶上同一份契約，所以切分不會靜默地丟掉時序。人別契約與方向契約同理：說話者與待辦負責人必須分開、方向不能補上缺少的姓名、未標記或混合的片段不能被指派給任何人。

### 為什麼「只有文字」是可測試的

| 保護 | 做法 |
|---|---|
| 不讀音訊 | `summary` 指令的程式路徑沒有音訊解碼或上傳實作 |
| 不讀聲音特徵 | 不開啟 `audio/` 或 `speaker-profiles/` |
| 不外洩到 process 清單 | 逐字稿透過 stdin 傳遞，不放進 process arguments |
| 不讀認證檔 | 只執行官方 `codex login status`，不開啟 Codex 的 token 檔 |
| 不受逐字稿注入 | prompt 明確要求把逐字稿視為不可信輸入、不得使用工具 |
| 不留下工作痕跡 | 每次呼叫都是 `--ephemeral`、`--sandbox read-only`、空白暫存工作目錄，且忽略使用者設定與專案規則 |

---

## 行事曆候選事件狀態機

行事曆擷取是摘要成功之後的**第二次獨立請求**，使用 `--output-schema` 搭配嚴格 JSON Schema，輸入只有摘要與逐字稿文字。**這次請求本身不會建立任何外部事件。**

```mermaid
stateDiagram-v2
    direction LR
    [*] --> pending: Codex 回傳合法候選<br/>寫入 SQLite
    pending --> created: 使用者逐筆確認<br/>或 auto_create 已一次同意
    pending --> dismissed: 使用者選擇略過
    pending --> failed: EventKit 寫入失敗
    failed --> pending: 重跑摘要時重試
    created --> [*]
    dismissed --> [*]

    note right of pending
        重跑同一天只會刷新
        尚未處理的候選
    end note
    note right of created
        EventKit 備註寫入
        SQLite 候選 ID
        中斷後可去重
    end note
```

- 日期明確但沒有時間 → 全天候選；日期無法解析 → 直接拒絕，不猜。
- 預設路徑要求**逐筆確認**；`auto_create` 需要一次明確 opt-in，之後由常駐的選單列程式注意到 `pending` 列並透過 EventKit 寫入。
- 每則 EventKit 備註都帶有 SQLite 候選 ID，所以狀態更新中斷後可在重試前去重。
- 擷取失敗或格式錯誤時，**既有的 pending 候選不受影響**，並在 Markdown 摘要中加上明顯警告。

---

## 程序拓撲

```mermaid
flowchart TB
    subgraph GUI["Aqua 登入階段"]
        APP["/Applications/FamilyRecorder.app<br/>原生 AppKit 選單列"]
    end

    subgraph AGENTS["使用者層級 LaunchAgent · 非 root daemon"]
        A1["com.familyrecorder.listener<br/>RunAtLoad + KeepAlive"]
        A2["com.familyrecorder.summary<br/>StartCalendarInterval"]
        A3["com.familyrecorder.menubar<br/>登入後啟動"]
    end

    subgraph RT["~/Library/Application Support/FamilyRecorder"]
        VENV["venv/bin/family-recorder<br/>Python CLI"]
        WC["whisper.cpp/ 與 ggml-*.bin"]
        UNI["解除安裝 FamilyRecorder.app"]
    end

    subgraph DATA["~/xvf3800-listener-data"]
        D1["audio/ · transcripts/ · summaries/"]
        D2["speaker-profiles/ · logs/ · control.json"]
        D3[("listener.sqlite3")]
    end

    A1 -->|"listener 服務"| APP
    A2 -->|"summary 服務"| APP
    A3 --> APP
    APP -->|"以 App 身分持有麥克風與行事曆授權"| VENV
    VENV --> WC
    VENV --> DATA
    APP -->|"開啟"| UNI
    UNI -.->|"停止三個 Agent 後移到垃圾桶"| RT
    UNI -.->|"完整模式才移除"| DATA

    classDef gui fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
    classDef agent fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef rt fill:#eceff1,stroke:#546e7a,color:#263238
    classDef data fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    class GUI gui
    class AGENTS agent
    class RT rt
    class DATA data
```

三個工作**全部是使用者層級 LaunchAgent**，不是 root daemon。launchd 環境變數中沒有任何 API key 或 Codex token；summary 工作只提供 `HOME`，讓官方 CLI 自己找到它保存的登入。

三個工作都關聯到 `/Applications` 裡的**同一個 App**，避免隱藏路徑或使用者層級路徑造成 Spotlight／TCC 身分快取不一致。macOS 因此在「隱私權與安全性 → 麥克風」顯示單一 `FamilyRecorder.app`，而不是 `python3.12`。

---

## 選單列控制路徑

Swift 選單列 App **不直接操作系統狀態**；它呼叫已安裝的 `family-recorder` CLI 來取得狀態、暫停／恢復、做目標式 YAML 編輯、產生摘要、執行診斷與註冊聲音樣本。

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者
    participant M as 選單列 App
    participant C as family-recorder CLI
    participant J as control.json
    participant L as listener 程序

    U->>M: 點選「暫停 15 分鐘」
    M->>C: family-recorder pause --minutes 15
    C->>J: 原子寫入暫停狀態與到期時間
    L->>J: 每秒檢查一次
    L->>L: 約 1 秒內關閉麥克風串流
    Note over L: 當下未完成的 chunk 直接丟棄，不保存
    J-->>L: 到期後自動恢復

    U->>M: 點選「錄製聲音樣本」
    M->>C: 先檢查麥克風授權
    alt 未授權
        C-->>M: 拒絕並提供系統設定連結
        M-->>U: 不啟動一段必定失敗的錄音
    else 已授權
        M->>C: enroll-speaker --name ... --seconds 15
        C->>J: 由選單發起的暫停
        C->>C: PCM 只留在記憶體 → 抽特徵 → 存 0600 JSON
        C->>J: 只有當暫停由選單自己發起時才恢復
    end
```

- 暫停狀態存在 `data_dir/control.json`，**不是只存在 UI 記憶體**；選單列程式重啟不會意外恢復錄音。
- Whisper 模型選項從**實際已下載**的 `ggml-*.bin` 探索而來，不是硬編清單。
- 目標式 config 編輯（`config_editor.py`）保留無關的 YAML 註解與值。
- 更動防幻覺門檻或本機模型會重啟 listener；Codex 摘要模型則在每次摘要執行時重新讀取，不需重啟。

---

## 解除安裝邊界

選單列**不會**內嵌刪除自己的 runtime，而是打開一個**獨立簽署的原生解除安裝器**。這樣它才能先停掉三個 LaunchAgent，再移動正在執行的選單列 App、Python 環境、whisper.cpp checkout 與模型。

```mermaid
flowchart TB
    START["使用者選擇解除安裝"] --> MODE{"選擇模式"}
    MODE -->|"只移除程式"| M1["停止三個 LaunchAgent<br/>移走 runtime · App · 模型<br/>保留 data_dir 與 config.yaml"]
    MODE -->|"完整移除"| M2["同上，另外處理資料根目錄"]
    M2 --> MARK{"資料目錄有<br/>.familyrecorder-data 標記？"}
    MARK -->|"有"| M3["移走整個資料根目錄"]
    MARK -->|"沒有 · 舊版或自訂共用路徑"| M4["只移走已知的 FamilyRecorder<br/>子目錄與資料庫<br/>無關檔案原地保留"]
    M1 & M3 & M4 --> TRASH["全部移到同一個<br/>加時間戳的垃圾桶資料夾"]
    TRASH --> REC["清空垃圾桶前都還能復原"]

    SAFE["安全檢查：拒絕以<br/>/ · 使用者家目錄 · 垃圾桶<br/>LaunchAgents 目錄作為移除目標"] -.-> MARK
    OUT["明確在邊界之外：<br/>ChatGPT／Codex 登入 · Homebrew 套件<br/>Python · Git · CMake · PortAudio<br/>GitHub repo · 已下載的 DMG"] -.-> TRASH

    classDef safe fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef warn fill:#fff8e1,stroke:#f9a825,color:#e65100
    class SAFE,REC,M4 safe
    class OUT warn
```

---

## 信任邊界總結

```mermaid
flowchart LR
    subgraph DEV["🎙️ 裝置"]
        RAW["原始四麥克風訊號"]
    end
    subgraph MAC["🔒 這台 Mac"]
        WAVF["WAV 音訊"]
        FEAT["聲音特徵向量"]
        TEL["DoA · Speech Energy"]
        AUDIT["攔截稽核記錄"]
        SQLITE[("SQLite")]
        TXT["逐字稿文字"]
    end
    subgraph NET["☁️ 網路"]
        CHATGPT["你自己的 ChatGPT 帳號"]
        HF["Hugging Face<br/>whisper.cpp 模型下載"]
        BREW["Homebrew<br/>相依套件"]
    end
    subgraph MACOS["🍎 macOS 系統服務"]
        EVENTKIT["EventKit → 行事曆 App<br/>→ 已加入的 Google 帳號"]
    end

    RAW ==>|"USB · 韌體處理後"| WAVF
    RAW ==> TEL
    WAVF ==> FEAT
    WAVF ==> TXT
    TEL ==> SQLITE
    FEAT ==> SQLITE
    AUDIT ==> SQLITE
    TXT -->|"每日一次 · stdin"| CHATGPT
    HF -.->|"僅安裝與切換模型時"| MAC
    BREW -.->|"僅安裝時"| MAC
    TXT -->|"僅在啟用行事曆時<br/>候選事件標題與時間"| EVENTKIT

    WAVF -.-x NET
    FEAT -.-x NET
    TEL -.-x NET
    SQLITE -.-x NET

    classDef never fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef leaves fill:#fff8e1,stroke:#f9a825,color:#e65100
    class WAVF,FEAT,TEL,AUDIT,SQLITE never
    class TXT leaves
```

`-.-x` 的四條線代表**從不離開這台 Mac**。唯一跨越邊界的是逐字稿文字，每天一次。完整威脅模型見 [隱私與信任邊界](privacy.md)。

---

## 明確非目標

這些不是「還沒做」，而是**刻意不做**：

- ❌ 鑑識等級的聲紋辨識、身分驗證，或逐字級 diarization
- ❌ 把 DoA 當成身分、距離、房間座標，或「這段話整段都是同一個人說的」的證明
- ❌ 隱蔽錄音
- ❌ 即時雲端轉錄
- ❌ 上傳或遠端備份原始音訊
- ❌ 自動執行推測出來的待辦或提醒
- ❌ 網頁儀表板

---

## 延伸閱讀

- [資料與 SQLite](data-model.md) — 每一張表與欄位的完整定義
- [隱私與信任邊界](privacy.md) — 威脅模型與同意
- [設定參考](configuration.md) — 影響上述每一個決策點的參數
- [應用場景指南](use-cases.md) — 同一套架構怎麼換成別的服務
