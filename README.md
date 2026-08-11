# FamilyRecorder

在 Apple Silicon Mac 上把 **XVF3800 USB 麥克風陣列**變成常駐、隱私優先的家庭聲音日誌：

```text
XVF3800 / XMOS
        ├── UAC2 音訊 ──► 30 秒 PCM ──► VAD ──► whisper.cpp 時間片段
        └── USB 控制 ──► 每 0.25 秒 DoA／語音旗標 ───┐
                    本機家庭人聲近似比對 ────────────┤
                                                     │ 每小段對齊時間＋音色＋方向
                                ┌────────────────────┴─────────────┐
                                ▼                                  ▼
              含「可能是誰／哪個方向」的逐字稿              listener.sqlite3
                                │
                                │ 每日排程；只讀取並上傳文字
                                ▼
                    官方 Codex CLI
                    （ChatGPT 網頁登入）
                                │
                                ▼
                      summaries/YYYY-MM-DD.md
```

原始 WAV 不會交給雲端摘要程式。每日摘要沿用官方 Codex CLI 的「Sign in with ChatGPT」登入，不使用 OpenAI API key，也不讀取或複製瀏覽器 cookie／OAuth token。

> 使用前請先取得所有可能被錄音者的明確同意，清楚標示正在收音，並依所在地規範使用。本專案不提供隱蔽錄音功能。

## 功能

- 列出所有 macOS 輸入裝置，自動優先選擇名稱含 `XVF3800`、`XMOS`、`microphone array`、`USB` 的 UAC 裝置；預設不會悄悄改用 Mac 內建麥克風。
- 連續讀取 30 秒 chunk。XVF3800 韌體若固定為 48 kHz，會先按裝置預設取樣率擷取，再於本機轉成 Whisper/VAD 使用的 16 kHz 單聲道 PCM16。
- RMS silence gate 與 WebRTC VAD 雙重過濾，安靜片段不落地、不進 Whisper。
- 呼叫本機 `whisper.cpp`，預設 `zh`、`large-v3-turbo`、8 threads；Apple Silicon 安裝時開啟 Metal。
- 每日 Markdown 逐字稿，以及含時間、音量、SNR、speech ratio、WAV 路徑與狀態的 SQLite 索引。
- 原始音訊保留天數與「成功轉錄後立即刪除」兩種 policy。
- 每日只把逐字稿文字透過官方 `codex exec` 送到已登入的 ChatGPT 帳號；摘要會按原始片段時間與本機近似人別建立事件時間軸及家庭成員重點，過長逐字稿則依完整段落切分後再保留時間、人別並去重整併。
- 三個使用者層級 LaunchAgent：listener 常駐、summary 依 YAML 指定時間每日執行、選單列控制登入後啟動。
- 原生 macOS 選單列圖示：查看狀態、定時暫停／恢復、開啟資料、下載／切換 Whisper 模型、切換摘要模型、立即摘要、重啟與系統檢查。
- 可從選單維護姓名與專有名詞清單；字詞會加入本機 Whisper 提示，並在辨識後保守校正無歧義的單一字差近似結果。
- 內建原生一鍵解除安裝：可只移除程式與模型並保留家庭資料，或把程式、模型、錄音、逐字稿、資料庫、人聲樣本與設定完整移到垃圾桶。
- 可設定 1–8 位已知家庭成員；每人主動錄製 15 秒樣本後，只在本機保存不可播放的聲音特徵，為逐字稿標示「可能：某人／可能多人／不確定」。
- 透過 XVF3800 獨立 USB 控制介面同步讀取 DoA（Direction of Arrival）；將 Whisper 的數秒級時間片段分別配對音色人別與方向，逐字稿及每日摘要同時保留兩種線索。
- 選單列可開關方向判斷、測試目前方向，並讓使用者站在指定位置說話，把該方向一鍵校準為房間的 `0° 正前方`。
- Google Calendar 為預設行事曆 provider：每位家庭成員可綁定多個日曆並指定預設；AI 只建立待確認候選事件，使用者確認後才透過 macOS 行事曆帳號寫入 Google Calendar。
- Mic placement test：A/B/C 等多個位置朗讀同一組 20 句固定句，比較 RMS、SNR、speech ratio、Whisper 文字與 CER（字元錯誤率）。

XMOS 官方文件指出，標準 UA 韌體會以 `XMOS XVF3800 Voice Processor` 顯示，USB Audio 可固定為 16 kHz 或 48 kHz；本專案因此同時支援名稱比對與取樣率 fallback。方向角不是 WAV 內的額外聲道，而是另外讀取 `DOA_VALUE`／波束控制資料；Seeed 官方工具也把 Auto selected beam 定義為 LED 指示所用的方向。參考：[XVF3800 硬體／UA 設定](https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/user_guide/02_setting_up_the_hardware.html)、[XVF3800 datasheet](https://www.xmos.com/documentation/XM-014888-PC/pdf/xvf3800_datasheet_v3.2.1.pdf)、[Seeed XVF3800 Host Control](https://github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY/blob/master/host_control/README.md)。

## 系統需求

- Apple Silicon Mac（`arm64`）
- macOS、使用者登入階段可使用的 USB 音訊裝置
- [Homebrew](https://brew.sh/)
- Homebrew `libusb`（安裝器會自動安裝）
- 約 2–4 GB 可用空間供程式、模型與 build；錄音資料另計，16 kHz mono PCM16 在持續有語音的極端情況約 2.8 GB／日
- 雲端摘要才需要網路、官方 Codex CLI，以及可使用 Codex 的 ChatGPT 帳號；不需要 API key。監聽、VAD、轉錄不需要網路

## 安裝

### DMG 圖形安裝（建議）

從 [GitHub Releases](https://github.com/pcpcchen-coder/FamilyRecorder/releases) 下載最新的 `FamilyRecorder-*-arm64.dmg` 與 `.sha256`，先核對 SHA-256，再開啟 DMG：

1. 執行「安裝 FamilyRecorder.app」。
2. 在視窗中選擇 `small`、`medium` 或建議的 `large-v3-turbo` 本機 Whisper 模型。
3. 若尚未安裝 Codex，按「安裝官方 Codex CLI」；再按「登入 ChatGPT」，瀏覽器會開啟官方登入頁。
4. 按「安裝 FamilyRecorder」。安裝器會從 DMG 內的 wheel 安裝本程式、以 Metal 編譯 whisper.cpp、下載選定模型，並建立 listener／summary／選單列工作。
5. 接上 XVF3800，依 macOS 提示允許「FamilyRecorder」使用麥克風。

同一個 DMG 也附有「解除安裝 FamilyRecorder.app」。平常可直接從選單列波形圖示選「解除安裝 FamilyRecorder…」；若選單列無法啟動，重新掛載 DMG 後打開解除安裝器即可，不需要使用終端機。

安裝器不會要求 OpenAI API key，也不會讀取 Codex 登入檔或 token；它只執行官方 `codex login`／`codex login status`。若一般瀏覽器返回流程受網路環境影響，可按「改用裝置碼登入」。登入也可稍後完成；這時錄音與本機轉錄仍會安裝，但每日摘要排程要在登入後重跑一次安裝器才會啟用。

目前公開 DMG 為 Apple Silicon、macOS 13+，並使用 ad-hoc 簽署，尚未經 Apple Developer ID 公證。第一次開啟若被 Gatekeeper 阻擋，請在 Finder 對安裝 app 按右鍵 →「打開」，並確認下載來源與 SHA-256。Homebrew 套件、whisper.cpp 原始碼／模型與 Codex CLI 仍需連線至其官方來源下載；FamilyRecorder wheel 與安裝介面本身包含在 DMG 內。

### 從原始碼安裝

```bash
git clone https://github.com/pcpcchen-coder/FamilyRecorder.git
cd FamilyRecorder
./scripts/install_mac.sh
```

腳本會：

1. 安裝 Python 3.12、PortAudio、CMake、Git。
2. 建立 `~/Library/Application Support/FamilyRecorder/venv`。
3. 安裝 FamilyRecorder。
4. checkout `whisper.cpp` v1.8.1，以 `GGML_METAL=ON` 編譯。
5. 下載 `ggml-large-v3-turbo.bin`。
6. 僅在不存在時建立 `~/.config/familyrecorder/config.yaml`，不覆蓋舊設定。
7. 偵測官方 Codex CLI／ChatGPT app，並顯示目前的 ChatGPT 登入狀態。

先安裝選單列程式，再進行硬體驗收：

```bash
./scripts/install_menubar.sh
```

它會用 Mac 內建的 Swift 工具編譯原生 `FamilyRecorder.app` 與「解除安裝 FamilyRecorder.app」，安裝到 runtime，並建立登入後自動啟動的內部工作；不需要另外安裝 GUI framework。首次啟動時會先顯示 FamilyRecorder 的用途說明；按「繼續並允許麥克風」後，再在 macOS 提示按「允許」。授權視窗不會卡住安裝器。listener、每日摘要與選單列雖然是三個內部工作，macOS 會把它們關聯到同一個 `FamilyRecorder.app`。

### macOS 中看到的名稱

從 0.9.0 起，正式安裝後的所有使用者可見名稱統一如下：

| macOS 畫面 | 顯示名稱 |
|---|---|
| 系統設定 → 隱私權與安全性 → 麥克風 | `FamilyRecorder.app`（macOS 在此頁自動顯示 `.app` 副檔名） |
| 系統設定 → 一般 → 登入項目與延伸功能 → App 背景活動 | `FamilyRecorder`（三個背景工作合併在同一 App 下） |
| 選單列、通知與麥克風授權提示 | `FamilyRecorder` |

`com.familyrecorder.listener`、`com.familyrecorder.summary`、`com.familyrecorder.menubar` 只是在 log 或診斷指令中使用的內部識別碼，不是 macOS 顯示給一般使用者的 App 名稱。麥克風頁和 Finder 一樣可能顯示 `FamilyRecorder.app`，其中 `.app` 是 macOS 顯示的應用程式副檔名，App 名稱仍是 `FamilyRecorder`。若是從 0.8.0 或更舊版本原地升級，舊的 `python3.12`／`family-recorder` 可能留在系統的歷史清單；可將它關閉，不需要刪除整個清單。新版錄音服務不再依賴該權限，而是由 `FamilyRecorder.app` 持有麥克風授權。

`whisper.cpp` 官方將 Apple Silicon／Metal 列為一級支援，且 `whisper-cli` 使用 16-bit WAV；參考其[官方 README](https://github.com/ggml-org/whisper.cpp)。

若想先用較小模型測試：

```bash
WHISPER_MODEL=medium ./scripts/install_mac.sh
```

安裝腳本會下載並自動把 YAML 的 `whisper.model_path` 切到 `ggml-medium.bin`；原有 config 其餘設定會保留。

## 第一次硬體 bring-up

先接上 XVF3800，再列出裝置：

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"

"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" list-devices
```

標準韌體通常類似：

```text
ID  Channels  Default Hz  Name
2   2         48000       XMOS XVF3800 Voice Processor
```

若自動比對不到，請在 YAML 設其中一個：

```yaml
audio:
  device_id: 2
  # 或 device_name_contains: "XMOS XVF3800 Voice Processor"
```

執行總體檢：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" doctor
```

到「系統設定 → 隱私權與安全性 → 麥克風」允許 `FamilyRecorder`，再透過原生 App 身分跑一個 30 秒 chunk。開始後持續說話，避免被 VAD 判成安靜：

```bash
"$RUNTIME/FamilyRecorder.app/Contents/MacOS/FamilyRecorder" \
  --service listener-once \
  --program "$RUNTIME/venv/bin/family-recorder" \
  --config "$CONFIG"
```

檢查結果：

```bash
cat "$HOME/xvf3800-listener-data/transcripts/$(date +%F).md"
sqlite3 "$HOME/xvf3800-listener-data/listener.sqlite3" \
  'select started_at, status, round(rms_dbfs,1), round(speech_ratio,2), text from segments order by id desc limit 5;'
```

若 `--once` 顯示 `Chunk skipped by silence/VAD gate`，代表整段未達門檻；這是正常的 privacy／storage 行為。測試時可暫時把 `vad.min_speech_ratio` 改成 `0.02`、`vad.min_rms_dbfs` 改成 `-55`，驗收後再改回範例值。

## 設定

完整範例見 [`config.example.yaml`](config.example.yaml)。常調整的欄位：

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `audio.chunk_seconds` | `30` | 連續錄音的 chunk 長度 |
| `audio.allow_default_input` | `false` | 找不到 XVF/XMOS/USB 時是否允許內建預設麥克風 |
| `vad.aggressiveness` | `2` | 0 最寬鬆、3 最嚴格 |
| `vad.min_speech_ratio` | `0.08` | 一個 chunk 至少多少比例判為語音 |
| `vad.min_rms_dbfs` | `-48` | 音量 gate；越接近 0 越嚴格 |
| `whisper.language` | `zh` | Whisper 語言 |
| `whisper.common_terms` | `[]` | 常用姓名／術語；可由選單逐行新增或移除，僅在本機使用 |
| `storage.keep_audio_days` | `7` | WAV 保留天數；0 代表只保留仍未超過當下 cutoff 的檔案 |
| `storage.delete_audio_after_transcription` | `false` | 成功或空白轉錄後立即刪 WAV；失敗 WAV 仍保留 |
| `speakers.enabled` | `false` | 有家庭成員時由選單自動開啟本機近似人別 |
| `speakers.members` | `[]` | 已知家庭成員姓名，選單可設定 1–8 人 |
| `speakers.min_similarity` | `0.82` | 聲音特徵最低相似度；提高可減少誤認、但增加「不確定」 |
| `speakers.min_margin` | `0.025` | 第一名至少要比第二名高出的差距 |
| `speakers.dominance_threshold` | `0.65` | 一個 chunk 內必須有多少分析視窗同意主要人選 |
| `direction.enabled` | `true` | 同步讀取 XVF3800 的本機方向遙測；失敗時錄音仍會繼續 |
| `direction.sample_interval_seconds` | `0.25` | 方向取樣間隔；預設每秒 4 次 |
| `direction.front_angle_degrees` | `0` | 哪個 XVF3800 原始角度代表房間正前方；建議由選單校準 |
| `direction.min_speech_samples` | `3` | 一個文字時間片段至少需要幾個帶語音旗標的方向樣本 |
| `direction.cluster_tolerance_degrees` | `35` | 相近方向合併容許角度 |
| `direction.multiple_direction_min_ratio` | `0.25` | 第二方向至少佔多少語音樣本才標示多方向 |
| `calendar.provider` | `google` | 預設且目前支援的行事曆 provider |
| `calendar.enabled` | `false` | 選定預設 Google Calendar 後由選單自動開啟候選事件 |
| `calendar.default_calendar_id` | 空字串 | 全家事件或無法判斷成員時使用的預設日曆 |
| `calendar.member_calendar_ids` | `{}` | 每位家庭成員可使用的多個 Google Calendar；由選單設定 |
| `calendar.member_default_calendar_ids` | `{}` | 每位成員在 AI 無法精確分類時的回退日曆 |
| `summary.model` | 空字串 | 沿用 ChatGPT 帳號目前可用的 Codex 預設模型；填值才固定模型 |
| `summary.codex_binary_path` | `codex` | 會搜尋 PATH、ChatGPT.app 與常見 Homebrew 位置 |
| `summary.timeout_seconds` | `900` | 每次 Codex 摘要最長等待秒數 |
| `summary.max_input_chars` | `300000` | 超過時切成多段摘要，再做一次最終去重整併 |
| `summary.prompt` | 內建繁中格式 | 可自訂摘要重點；安全規則與事件時間規則仍由程式強制附加 |
| `summary.hour` / `minute` | `0` / `10` | LaunchAgent 每日時間；修改後重跑安裝摘要腳本 |

## 每日純文字摘要

### 摘要包含哪些內容

預設輸出繁體中文 Markdown，包含：

1. 事件時間軸；保留約略時間與可能說話者。
2. 家庭成員重點；依逐字稿實際出現的「可能說話者」分組。
3. 對話方向與人別線索；同列時間、可能說話者與來源方向。
4. 今日重要消息。
5. 決策與承諾。
6. 待辦事項；分開保留可能說話者、明確指派的負責人、提出時間與期限。
7. 值得追蹤的想法或靈感。
8. 人名、專案名與產品名等關鍵實體。
9. 可能辨識錯誤或需要人工確認的片段。
10. 100 字內的今日摘要。

時間來自每日逐字稿的段落標題，而不是讓雲端模型猜測。例如原始資料：

```markdown
### 19:40:07–19:40:12 — 可能：家人二（87%） — 方向：左側 92°；穩定度 80%

明天記得去拿包裹，九點前要出門。
```

摘要會使用類似以下格式：

```markdown
## 事件時間軸

- 約 19:40｜可能說話者：家人二｜來源方向：左側 92°：提到明天要拿包裹，並希望九點前出門。

## 對話方向與人別線索

- 約 19:40｜可能說話者：家人二｜來源方向：左側 92°。

## 家庭成員重點（依可能說話者）

### 家人二

- 約 19:40：提醒明天拿包裹，並提到九點前出門。

## 待辦事項

- 約 19:40｜可能說話者：家人二：明天拿包裹；預計九點前出門。負責人需確認。
```

`19:40:07–19:40:12` 是 Whisper 文字片段對應的音訊時間範圍，不代表每個字都有鑑識級精準時間。摘要因此只顯示到分鐘並加上「約」；事件跨越相鄰片段時可顯示 `約 19:40–19:41`。無法對應來源段落的資訊必須標示「時間不明」，不可拿摘要執行時間代替，也不可從對話語意自行推測時間。

時間、人別與方向規則都由程式固定附加到每一次 Codex 請求，包括長逐字稿的每個分段與最後整併；即使現有 `config.yaml` 使用舊版或自訂 `summary.prompt`，升級後也會生效。長逐字稿依完整的 `### 時間 — 人別 — 方向` 段落切分，避免標題與內容被拆到不同請求。所有時間均沿用錄音 Mac 的本地日期與時區。

人別是本機聲音特徵的近似結果，不是已確認身分。摘要一律使用「可能說話者」措辭；同一事件跨多位成員時可列多位或標示「可能多人」，把握不足則保留「不確定／人別未提供」。說話者只代表該片段的可能主要聲音，不能直接推定是事件執行者或待辦負責人。

方向是聲源相對於麥克風的角度，不是人的姓名。當同一文字片段同時有穩定音色與穩定方向時，摘要會並列兩者作為相互參考；家庭成員移動、兩人站在同方向、牆面反射、電視或多人同時說話都可能使方向不準。沒有音色姓名的片段絕不會只靠方向硬指定某位家人。

### 登入與手動執行

先用官方 Codex CLI 打開瀏覽器登入 ChatGPT；這是一次性的互動步驟：

```bash
codex login
codex login status
```

若只安裝 ChatGPT macOS app，FamilyRecorder 也會自動尋找 app 內附的官方 Codex。`doctor` 應顯示 `ChatGPT login: Logged in using ChatGPT`。登入由 Codex 自己保存與更新；FamilyRecorder 不會開啟其認證檔，更不會把 token 放進 YAML、plist 或 log。

手動驗證指定日期：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" summary --date 2026-08-09
```

不帶 `--date` 時會整理 Mac 本地日期的昨天，與每日排程相同。選單列的「立即整理今天」會明確傳入今天日期。重跑同一天會覆寫 `summaries/YYYY-MM-DD.md`，並更新 SQLite `summaries` 表的同一筆日期索引，不會建立多份互相衝突的摘要。

### 長逐字稿與純文字邊界

摘要使用官方非互動模式 `codex exec`。每次執行固定為 `--ephemeral`、`--sandbox read-only`，在新的空白暫存目錄內工作，且不載入使用者 MCP／專案規則；prompt 也要求不得呼叫工具或遵循逐字稿內的指令。參考：[Codex 登入](https://learn.chatgpt.com/docs/auth)、[Codex 非互動模式](https://learn.chatgpt.com/docs/non-interactive-mode)。

`summary.model` 留空會使用帳號／Codex 的預設模型；若在選單列輸入自訂模型，FamilyRecorder 會在執行時以明確的 `--model` 選擇覆蓋預設。這符合官方 [Codex config reference](https://learn.chatgpt.com/docs/config-file/config-reference) 的優先順序。

隱私邊界是程式結構上的限制：`summary` 指令只開啟 `transcripts/YYYY-MM-DD.md`，不會讀取 `audio/` 或 `speaker-profiles/`。逐字稿透過 stdin 傳給 Codex，不出現在 process arguments；若超過 `summary.max_input_chars`，仍只分段傳送文字。每段先保留事件時間、可能說話者與不確定性，最後才把同一天的中間整理去重合併。

請注意，逐字稿文字本身可能包含敏感內容、近似人別姓名與家庭事件；啟用前應先檢視 prompt、ChatGPT 資料設定與家庭共識。FamilyRecorder 不會把聲音、聲音特徵、SQLite 或本機檔案路徑附加到摘要請求。

## Google Calendar 候選事件

FamilyRecorder 預設支援 Google Calendar，但不另存 Google 密碼或 OAuth token。它使用已加入 macOS「Internet 帳號」並在「行事曆」App 中同步的 Google 帳號；第一次使用會由 macOS 詢問 `FamilyRecorder` 行事曆權限。

1. 若 Mac 尚未加入 Google 帳號，先到「系統設定 → Internet 帳號 → 加入帳號 → Google」，並開啟「行事曆」。
2. 點 FamilyRecorder 選單 →「Google Calendar」→「連接／選擇預設 Google Calendar…」。
3. 在「家庭成員日曆對應」中，為每位成員勾選一個或多個可用日曆，再從下方指定該成員的預設日曆。
4. 每日摘要或「立即整理今天」會先產生人類閱讀的摘要，再由 ChatGPT 執行一次具有固定 JSON 結構的候選事件擷取；日期明確但沒有時間（例如「明天考試」）會成為全天候選，日期也不明確時才略過。它可依成員及日曆顯示名稱建議路由，無法確定時回退到成員預設或全家預設。
5. 從「待確認事件」檢視標題、時間、成員與目的日曆，按「確認建立」後才真正寫入；也可改選其他 Google Calendar 或直接略過。

候選事件存在 SQLite `calendar_candidates` 表，狀態為 `pending`、`created`、`dismissed` 或 `failed`。重新執行同一天摘要只會刷新尚未處理的候選項目，不會重建已確認或已略過的同一事件。若事件擷取的第二次 ChatGPT 請求失敗，摘要檔會顯示警告，且程式會保留既有待確認項目，不會因暫時性錯誤把它們清空。啟用這項功能後，送往 ChatGPT 的純文字指示會額外包含家庭成員姓名、可選日曆顯示名稱及本機 EventKit ID，讓 AI 建議路由；Google Calendar 的實際內容不會被讀取或上傳。

## 安裝常駐工作

務必先通過上面的單次錄音驗收，且已執行 `install_menubar.sh`，再安裝 listener：

```bash
./scripts/install_launchd.sh
```

安裝每日摘要：

```bash
./scripts/install_daily_summary.sh
```

檢查狀態與 log：

```bash
launchctl print "gui/$UID/com.familyrecorder.listener"
launchctl print "gui/$UID/com.familyrecorder.summary"
tail -f "$HOME/xvf3800-listener-data/logs/listener.log"
tail -f "$HOME/xvf3800-listener-data/logs/listener.error.log"
```

## 選單列控制

安裝後，右上角會出現波形圓形圖示；暫停時變成 pause 圖示，listener 異常則顯示警告圖示。點開後可使用：

- 顯示「錄音中／已暫停／服務未執行」、目前 Whisper 與摘要模型。
- 暫停 15 分鐘、1 小時或直到手動恢復；listener 每秒檢查一次，約 1 秒內關閉麥克風串流，當下未完成的 chunk 會丟棄而不保存。
- 快速開啟今天的逐字稿／摘要，以及全部資料、音訊、log、設定檔。
- 從實際已下載的 `ggml-*.bin` 清單切換本機 Whisper；切換後會重啟 listener。
- 在「本機 Whisper → 下載其他模型…」依標準、量化省空間、舊版相容三組直接下載新的多語模型；會顯示預估容量，支援失敗後續傳，完成 GGML 格式驗證後才切換並重啟 listener，原有模型不會刪除。
- 摘要模型可使用 ChatGPT 帳號預設，或輸入帳號實際可用的自訂 Codex 模型名稱。
- 在「更換模型 → ChatGPT 摘要」以多行編輯器自訂每日摘要 Prompt，或一鍵恢復內建格式；變更只套用到之後產生或重新執行的摘要。
- 在「常用字詞校正」逐行維護姓名與術語，例如 `陳樂融`；儲存後會重啟 listener 套用。
- 在「家庭成員與人聲」編輯成員、查看註冊狀態、錄製／更新或刪除個別聲音樣本。
- 在「Google Calendar」選擇全家預設日曆、為每位成員綁定多個日曆，並逐筆確認 AI 候選事件。
- 立即整理今天、重新啟動錄音服務、執行完整 `doctor` 檢查。
- 使用「解除安裝 FamilyRecorder…」打開獨立解除安裝器；主選單被關閉後清理仍會繼續。

暫停狀態存在 `data_dir/control.json`，不是只存在 UI 記憶體；因此選單列程式重啟不會意外恢復錄音，定時暫停到期則由 listener 自動恢復。選「結束選單列程式」只會關閉圖示，不會停止 listener；重新登入或重跑安裝腳本即可再次顯示。

下載清單對應專案固定使用的 whisper.cpp v1.8.1 官方模型清單。FamilyRecorder 預設為中文，因此不顯示 `.en` 英文限定版；可選 Tiny、Base、Small、Medium、Large v1/v2/v3、Large v3 Turbo 及其多語 Q5／Q8 量化版本。模型從 whisper.cpp 官方下載腳本指定的 Hugging Face repository 取得，名稱經 allowlist 驗證，未完成的檔案以 `.partial` 保存供下次續傳。

也可使用指令下載並切換，例如：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  download-whisper-model --model small-q5_1
```

## 一鍵解除安裝

建議使用圖形介面：

1. 點選單列波形圖示 →「解除安裝 FamilyRecorder…」。
2. 選擇「只移除程式，保留家庭資料與設定」或「完整移除，包括所有模型、錄音與紀錄」。
3. 確認畫面列出的程式／模型、家庭資料與設定容量，再按解除安裝。
4. 所有選定內容會先移到同一個垃圾桶子資料夾；確認不需復原後再清空垃圾桶。

「只移除程式」會停止並移除三個 LaunchAgent，移走 Python runtime、選單列 App、解除安裝器、whisper.cpp 與所有本機 Whisper 模型，但保留 `data_dir` 和 `config.yaml`，方便日後重新安裝。「完整移除」還會一併移走：

- 原始 WAV、逐字稿、每日摘要與 SQLite。
- 人聲特徵、擺位測試、暫停狀態與 logs。
- FamilyRecorder 設定及其安裝備份。
- 選單列 App 的 FamilyRecorder 麥克風與行事曆權限紀錄。

兩種模式都不會登出或移除 ChatGPT／Codex，不會刪除 Homebrew、Python、Git、CMake、PortAudio 等可能由其他程式共用的工具，也不會刪除 GitHub repo、本機原始碼 checkout 或另外下載的 DMG。

資料目錄會建立 `.familyrecorder-data` 所有權標記，讓解除安裝器確認它是 FamilyRecorder 專用資料夾。為相容沒有標記的舊版或自訂共用路徑，完整移除時只會搬走已知的 FamilyRecorder 子目錄與資料庫，不會把整個 Documents 或其他共用資料夾移走。

若圖形介面無法使用，可從原始碼 checkout 執行同一套安全解除安裝流程：

```bash
./scripts/uninstall_family_recorder.sh inspect
./scripts/uninstall_family_recorder.sh uninstall keep-data  # 保留家庭資料與設定
./scripts/uninstall_family_recorder.sh uninstall all        # 完整移除
```

舊的 `./scripts/uninstall_launchd.sh` 只適合暫時停止並移除三個 LaunchAgent，不會刪除其他內容。

listener 遇到拔線或裝置暫時不可用時會依 `audio.retry_seconds` 重試；重新插入後會再次自動選擇裝置。

## 家庭成員近似人別

這項功能特別針對「少數、固定、已知家庭成員」設計，不是泛用語者分離或身分驗證。首次使用：

1. 點選選單列 FamilyRecorder →「家庭成員與人聲」→「設定家庭成員…」。
2. 每行輸入一位成員；姓名只進入這台 Mac 的私人 YAML，不必寫進公開 repo。
3. 逐一點選成員 →「錄製聲音樣本…」。第一次使用時，依 macOS 提示允許 FamilyRecorder 使用麥克風；按下開始後，浮動視窗會在倒數與 15 秒錄音期間持續顯示朗讀範例、剩餘時間及目前狀態。錄音服務會暫停，完成後自動恢復。
4. 每人最好站在平常說話的位置、以自然音量錄製；環境、麥克風位置或聲音明顯改變時可重新錄製。兒童聲音隨成長變化，建議定期更新。

Whisper 完成一個 30 秒 chunk 後，系統會使用其 JSON 時間戳拆成通常數秒長的文字片段，再對各片段的音訊範圍分別比較音色、頻譜與音高特徵。只有相似度、第一／第二名差距與分析視窗一致性都達標才顯示姓名。多人同時說話、電視、距離過遠或把握不足時，會標「可能多人」或「不確定」。這比整個 30 秒只標一人細緻，但仍是「Whisper 片段級」而不是逐字聲紋鑑識；錯認仍然可能發生。

註冊音訊只存在記憶體中，產生特徵後即丟棄，不會建立 WAV。特徵以權限 `0600` 保存在 `speaker-profiles/`，不會送給 Whisper、Codex 或其他雲端服務；但它仍屬敏感個人資料，應保護 Mac 帳號與備份。刪除成員或選「刪除聲音樣本」會移除對應檔案。

也可用指令設定通用範例與註冊（listener 執行時要先暫停）：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  set-speakers --name "我" --name "家人二" --name "家人三"
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" pause
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  enroll-speaker --name "我" --seconds 15
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" resume
```

## 聲音方向＋音色人別

XVF3800 的 UAC 音訊只有處理後聲道；DoA 由同一台裝置的 USB vendor control 介面另行讀取。FamilyRecorder 在每個 30 秒錄音期間預設每 0.25 秒保存一次原始角度與 `speech_detected`，再按 Whisper 文字片段的起訖毫秒篩選同時間樣本。相近角度會做環狀分群，因此 `358°` 與 `2°` 會視為同方向；若第二個相隔明顯的方向達到設定比例，該片段標成「方向：多個」。

第一次使用建議校準房間方向：

1. 點選選單列 FamilyRecorder →「聲音方向」→「把目前位置校準為正前方…」。
2. 站在你想定義為正前方的位置，只讓一個人持續自然說話 4 秒。
3. 完成後，逐字稿顯示的 `0°` 是該正前方；`90°` 為左側、`180°` 為後方、`270°` 為右側。
4. 移動或旋轉麥克風後必須重新校準；只墊高而未旋轉通常不需要。

選單中的「測試目前方向…」可在不寫入逐字稿的情況下顯示方位、角度、穩定度與有效樣本數。也可使用：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" probe-direction --seconds 2
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" calibrate-direction --seconds 4
```

方向與音色的結合方式是「同一時間片段並列兩項獨立證據」，不是用座位直接綁定姓名。例如：

```markdown
### 19:40:07–19:40:12 — 可能：爸爸（87%） — 方向：左側 92°；穩定度 80%

明天記得去拿包裹。
```

若爸爸移到別的位置，姓名仍由音色近似判斷，方向跟著新的聲源位置改變。兩人坐在相同方位時方向無法分辨兩人；兩個明顯方向或音色判斷衝突時，摘要會保守標示需人工確認。原始 DoA 取樣與聲音特徵只留在本機 SQLite；雲端每日摘要只會收到逐字稿標題中的文字化方向，不會收到音訊、聲音特徵或逐筆 USB 遙測。

## Mic placement test

建議先比三個位置，例如「茶几中央墊高 10 cm」、「櫃上」、「Mac 旁」。每個位置會使用完全相同的 20 句；預設每句錄 8 秒：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  placement-test --positions "茶几中央" "櫃子上" "Mac旁"
```

可自訂秒數或固定句檔（UTF-8，每行一句）：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  placement-test --positions A B C --seconds 10 --sentences-file ./my-sentences.txt
```

輸出位於：

```text
~/xvf3800-listener-data/placement-tests/YYYYMMDD-HHMMSS/
├── 01-A/01.wav ...
├── 02-B/01.wav ...
├── 03-C/01.wav ...
└── report.md
```

選擇時以「**較低 CER**」為主，再看較高 SNR、穩定的 speech ratio 與不爆音的 RMS。若 SNR 顯示 `n/a`，通常是整句全部被 VAD 判成語音或全部判成背景，缺少可比較的噪音 frame；請在按下 Enter 後留約一秒環境聲再朗讀。

實體放置建議：水平、接近談話區幾何中心、離桌面約 5–15 cm，底部用 3–6 mm 矽膠腳墊或穩固小支架，避免直接接觸敲桌與風扇振動。

## 資料與 SQLite

```text
~/xvf3800-listener-data/
├── .familyrecorder-data                   # 安全解除安裝用的專用目錄標記
├── audio/YYYY-MM-DD/HHMMSS_microseconds.wav
├── transcripts/YYYY-MM-DD.md
├── summaries/YYYY-MM-DD.md
├── placement-tests/YYYYMMDD-HHMMSS/
├── speaker-profiles/speaker-<雜湊>.json # 本機聲音特徵；無原始註冊音訊
├── control.json                         # 僅在暫停時存在
├── logs/
└── listener.sqlite3
```

`segments.status`：

- `transcribed`：Whisper 有文字，已附加到當日 Markdown。
- `empty`：Whisper 成功但沒有文字，不寫 Markdown。
- `failed`：Whisper 失敗；WAV 一律保留直到 retention 到期，以利排查。

人別欄位為 `speaker_name`、`speaker_confidence` 與 `speaker_status`；`speaker_status` 可能為 `recognized`、`mixed`、`uncertain` 或 `disabled`。`speaker_confidence` 是本機特徵相似度，不是統計校準後的身分機率。

方向摘要欄位為 `direction_raw_angle_deg`、校準後的 `direction_angle_deg`、`direction_label`、`direction_confidence`（主要方向的樣本占比）、`direction_status`、`direction_spread_deg` 與樣本數；`direction_status` 可能為 `detected`、`multiple`、`uncertain`、`unavailable` 或 `disabled`。`direction_samples` 表另外保存每個文字片段內的毫秒 offset、原始角度及語音旗標，並以 `segment_id` 連回 `segments`。

`summaries` 表以 `summary_date` 為主鍵，另存摘要檔路徑、實際選用的模型標記與建立時間。重新整理同一天時會更新該列。Markdown 摘要中的事件時間仍以逐字稿標題為準，SQLite 的 `created_at` 只是摘要產生時間。

手動執行 retention：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" cleanup
```

## 開發與測試

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest --cov=family_recorder
```

在 Apple Silicon Mac 建置可攜 DMG：

```bash
./scripts/build_dmg.sh
```

產物為 `dist/FamilyRecorder-<版本>-arm64.dmg` 與對應的 `.sha256`。若要公開散布且不顯示 Gatekeeper 未公證警告，發行者還需使用 Developer ID Application 憑證簽署並送 Apple notarization；一般 Apple Development 憑證不等同公開發行公證。

硬體不在 CI 測試範圍；裝置選擇、雙聲道 downmix／取樣率轉換、VAD 指標、Whisper CLI 介面、SQLite migration／Markdown、人聲特徵儲存與近似分類、retention、純文字摘要與 CER 報告都有隔離測試。

## 驗收清單

1. `list-devices` 看得到 XVF3800/XMOS，`doctor` 選到正確裝置。
2. `listen --once` 後 WAV 是 16 kHz、mono、PCM16。
3. 安靜 30 秒不產生 WAV／逐字稿；持續說話會產生。
4. 當日 Markdown 有正確時間標題與繁中內容。
5. SQLite 最新列的 `status='transcribed'`，且 RMS／speech ratio 合理。
6. 拔掉 XVF3800，listener log 顯示 retry；插回後恢復。
7. 把 `keep_audio_days` 暫設為 0，執行 `cleanup` 可移除舊 WAV，不動逐字稿。
8. 手動 `summary --date ...` 只產生 Markdown summary，雲端程式路徑未讀 WAV 或聲音特徵。
9. `codex login status` 與 `doctor` 都顯示 ChatGPT 已登入；YAML、plist、環境變數與 Python dependencies 均沒有 OpenAI API key。
10. 重開機／重新登入後三個 `launchctl print` 工作存在，右上角有 FamilyRecorder 圖示。
11. 選單列暫停後不再產生 chunk，恢復後 listener 繼續；模型清單與資料夾捷徑可用。
12. A/B/C placement report 有每句轉錄、RMS、SNR、speech ratio、CER 與彙總表。
13. 設定三位測試成員並完成樣本後，選單顯示 3/3；逐字稿出現「可能：某人」或保守的「可能多人／不確定」，SQLite 三個 speaker 欄位同步。
14. 刪除其中一位樣本後，對應 `speaker-*.json` 消失，其他成員不受影響。
15. 摘要的「事件時間軸」、重要消息、決策與待辦均保留 `約 HH:MM`／時間區間；無法對應者標示「時間不明」。
16. 摘要對每個有來源人別的重要項目保留「可能說話者」，並有「家庭成員重點」分組；可能多人、不確定及未標記內容不會硬分配，說話者也不會自動成為待辦負責人。
17. 把測試逐字稿限制成多段輸入後，每一段仍保留其 `### 時間 — 可能：某人` 標題，最終整併請求也包含相同人別契約。
18. 在隔離暫存 HOME 驗證解除安裝兩種模式：保留模式不碰逐字稿與設定；完整模式移除全部 FamilyRecorder 內容；無標記的共用資料夾保留無關檔案。
19. DMG 同時包含安裝器與解除安裝器，兩者簽章、版本與內含腳本均通過驗證。
20. `ruff check .`、`ruff format --check .`、`pytest`、Swift typecheck、plist／shell 語法與套件建置全數通過。
21. `doctor` 的 XVF3800 direction telemetry 顯示 OK；選單「測試目前方向」能在說話時回傳角度。
22. 校準正前方後，從正前方、左側與右側各說一句，逐字稿分別接近 `0°`、`90°`、`270°`，SQLite 同步保存方向摘要與逐筆樣本。
23. 同一 30 秒內從兩個不同方向輪流說話時，Whisper 時間片段各自取得相符方向；同時或快速交疊時保守標示多方向／不確定。
24. 每日摘要包含「對話方向與人別線索」，重要項目保留來源方向；沒有音色姓名時不會只靠方向指定家人。
25. Google Calendar 未確認前不建立任何事件；為成員綁定多個日曆後，AI 建議路由可回退到成員／全家預設，確認建立與略過都會更新 SQLite 狀態。

## 常見問題

**找不到 XVF3800**：先在「系統資訊 → USB」與「音訊 MIDI 設定」確認裝置，再跑 `list-devices`。某些板子顯示 `XMOS XVF3800 Voice Processor`，不只 `XVF3800`。

**Invalid sample rate**：確認 YAML 目標為 16000。程式會在 16 kHz 開啟失敗時改用裝置宣告的 48 kHz，再於本機轉成 16 kHz；若裝置預設值不正確，先在「音訊 MIDI 設定」選 16 kHz 或 48 kHz。

**LaunchAgent 沒收到聲音**：先使用「第一次硬體 bring-up」中的 `FamilyRecorder --service listener-once` 指令測試；檢查「系統設定 → 隱私權與安全性 → 麥克風」中 `FamilyRecorder.app` 已開啟，以及 `listener.error.log`。macOS 麥克風權限是每台機器的互動授權，安裝腳本不能替你繞過。

**系統設定仍顯示 `python3.12` 或 `family-recorder`**：這是 0.8.0 以前直接啟動 Python worker 留下的歷史項目。先確認已升級到 0.9.0、重跑 `install_menubar.sh`、`install_launchd.sh` 與 `install_daily_summary.sh`，再把舊項目的切換鈕關閉；目前使用中的麥克風項目應是 `FamilyRecorder.app`，背景工作則顯示 `FamilyRecorder`。不要為了清掉一列歷史紀錄而重設所有 App 的麥克風權限。

**一直被 VAD 略過**：查看 log 的 RMS 與 speech ratio，先以 `-55 dBFS`／`0.02` 測試，再逐步調嚴；也可用 placement test 比較實際位置。

**人別常顯示不確定／認錯人**：讓每位成員在相同麥克風位置重新錄製自然語音，避免電視、音樂與多人同時說話。若誤認多，提高 `min_similarity` 或 `min_margin`；若大多不確定，才小幅降低。這項功能不能用於門禁、付款、家長監護或任何需要確認身分的用途。

**方向顯示無法讀取**：確認是 VID `0x2886`／PID `0x001A` 的 reSpeaker XVF3800，執行 `brew install libusb`，再從選單執行「檢查系統狀態」。音訊仍可錄到並不代表 USB vendor control 一定可讀；FamilyRecorder 會保留錄音並把方向標成無法讀取，不會讓 listener 因方向功能停止。

**方向和人所在位置不一致**：先確認麥克風沒有旋轉，再重新執行「把目前位置校準為正前方」。牆面反射、電視、喇叭回音、多人同時說話或兩人位於相同方位都可能干擾 DoA。方向是輔助線索，不是人別或距離感測器。

**聲音樣本一直建立失敗**：確認「系統設定 → 隱私權與安全性 → 麥克風」中的 FamilyRecorder 已開啟。選單列程式會在錄製樣本前主動檢查權限；未允許時不會開始一段必定失敗的錄音，並可直接打開對應的系統設定頁。

**Whisper 變慢或發熱**：把模型改成 `medium` 或 `small` 並更新 YAML；不要只增加 threads。確認安裝輸出包含 Metal，且 `doctor` 指向正確 build。

**摘要沒有執行**：先跑 `codex login status` 與相同的手動 `summary` 指令；再檢查逐字稿日期、網路與 `summary.error.log`。若登入失效，互動執行 `codex login`。排程預設在 00:10 整理「昨天」。

**摘要沒有事件時間**：確認已升級到 0.6.0 以上，再對同一天重新執行 `summary --date YYYY-MM-DD`。舊摘要檔不會自行重寫；新版在每次單段、分段與最終整併請求都會附加時間輸出規則，現有自訂 prompt 不需手動修改。

**摘要沒有保留人別**：確認已升級到 0.8.0 以上，並先檢查當日逐字稿標題是否真的有「可能：姓名／可能多人／不確定」。舊摘要不會自動重寫；重新整理指定日期後，新版會在事件時間軸、家庭成員重點、消息、決策、待辦與想法中盡可能保留可能說話者。若來源片段本身沒有人別，摘要不會自行猜測。

**摘要沒有方向資訊**：方向功能只會影響升級後新產生的逐字稿片段。先確認逐字稿標題含「方向：…」，再重新整理指定日期；0.10.0 會要求每次分段與最終摘要保留來源方向，並新增「對話方向與人別線索」。

**摘要有日期／事件，但「待確認事件」是空的**：確認已升級到 0.11.1 以上，再重新執行同一天摘要。0.11.1 會在摘要完成後以獨立的結構化 ChatGPT 請求擷取行事曆候選；只有日期而沒有時間的事件會列為全天候選。摘要檔底部會明確顯示找到的候選數量、沒有找到，或擷取失敗警告。候選仍須在選單中按「確認建立」才會寫入 Google Calendar。

**選單列沒有圖示**：重跑 `./scripts/install_menubar.sh`，再檢查 `launchctl print "gui/$UID/com.familyrecorder.menubar"` 與 `menubar.error.log`。選單的「結束」是刻意正常退出，LaunchAgent 不會立即重開；重跑安裝腳本即可。

**解除安裝器顯示沒有找到安裝內容**：確認是以安裝 FamilyRecorder 的同一個 macOS 使用者登入。若只剩舊資料、選單列已損壞，可從最新版 DMG 直接打開「解除安裝 FamilyRecorder.app」。
