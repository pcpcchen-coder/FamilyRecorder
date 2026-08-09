# FamilyRecorder

在 Apple Silicon Mac 上把 **XVF3800 USB 麥克風陣列**變成常駐、隱私優先的家庭聲音日誌：

```text
XVF3800 / XMOS UAC2
        │
        ▼
本機 30 秒 PCM chunk ──► RMS + WebRTC VAD ──► whisper.cpp（zh / Metal）
              │                                      │
              └──► 本機家庭人聲近似比對 ────────────┤
                                                     │
                                ┌────────────────────┴─────────────┐
                                ▼                                  ▼
              含「可能是誰」的每日逐字稿                    listener.sqlite3
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
- 內建原生一鍵解除安裝：可只移除程式與模型並保留家庭資料，或把程式、模型、錄音、逐字稿、資料庫、人聲樣本與設定完整移到垃圾桶。
- 可設定 1–8 位已知家庭成員；每人主動錄製 15 秒樣本後，只在本機保存不可播放的聲音特徵，為逐字稿標示「可能：某人／可能多人／不確定」。
- Mic placement test：A/B/C 等多個位置朗讀同一組 20 句固定句，比較 RMS、SNR、speech ratio、Whisper 文字與 CER（字元錯誤率）。

XMOS 官方文件指出，標準 UA 韌體會以 `XMOS XVF3800 Voice Processor` 顯示，USB Audio 可固定為 16 kHz 或 48 kHz；本專案因此同時支援名稱比對與取樣率 fallback。參考：[XVF3800 硬體／UA 設定](https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/user_guide/02_setting_up_the_hardware.html)、[XVF3800 datasheet](https://www.xmos.com/documentation/XM-014888-PC/pdf/xvf3800_datasheet_v3.2.1.pdf)。

## 系統需求

- Apple Silicon Mac（`arm64`）
- macOS、使用者登入階段可使用的 USB 音訊裝置
- [Homebrew](https://brew.sh/)
- 約 2–4 GB 可用空間供程式、模型與 build；錄音資料另計，16 kHz mono PCM16 在持續有語音的極端情況約 2.8 GB／日
- 雲端摘要才需要網路、官方 Codex CLI，以及可使用 Codex 的 ChatGPT 帳號；不需要 API key。監聽、VAD、轉錄不需要網路

## 安裝

### DMG 圖形安裝（建議）

從 [GitHub Releases](https://github.com/pcpcchen-coder/FamilyRecorder/releases) 下載最新的 `FamilyRecorder-*-arm64.dmg` 與 `.sha256`，先核對 SHA-256，再開啟 DMG：

1. 執行「安裝 FamilyRecorder.app」。
2. 在視窗中選擇 `small`、`medium` 或建議的 `large-v3-turbo` 本機 Whisper 模型。
3. 若尚未安裝 Codex，按「安裝官方 Codex CLI」；再按「登入 ChatGPT」，瀏覽器會開啟官方登入頁。
4. 按「安裝 FamilyRecorder」。安裝器會從 DMG 內的 wheel 安裝本程式、以 Metal 編譯 whisper.cpp、下載選定模型，並建立 listener／summary／選單列工作。
5. 接上 XVF3800，依 macOS 提示允許麥克風權限。

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

第一次完成硬體驗收後，安裝選單列程式：

```bash
./scripts/install_menubar.sh
```

它會用 Mac 內建的 Swift 工具編譯原生 `FamilyRecorder.app` 與「解除安裝 FamilyRecorder.app」，安裝到 runtime，並建立登入後自動啟動的 `com.familyrecorder.menubar` LaunchAgent；不需要另外安裝 GUI framework。

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

到「系統設定 → 隱私權與安全性 → 麥克風」允許你使用的 Terminal，再跑一個 30 秒 chunk。開始後持續說話，避免被 VAD 判成安靜：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" listen --once
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
| `storage.keep_audio_days` | `7` | WAV 保留天數；0 代表只保留仍未超過當下 cutoff 的檔案 |
| `storage.delete_audio_after_transcription` | `false` | 成功或空白轉錄後立即刪 WAV；失敗 WAV 仍保留 |
| `speakers.enabled` | `false` | 有家庭成員時由選單自動開啟本機近似人別 |
| `speakers.members` | `[]` | 已知家庭成員姓名，選單可設定 1–8 人 |
| `speakers.min_similarity` | `0.82` | 聲音特徵最低相似度；提高可減少誤認、但增加「不確定」 |
| `speakers.min_margin` | `0.025` | 第一名至少要比第二名高出的差距 |
| `speakers.dominance_threshold` | `0.65` | 一個 chunk 內必須有多少分析視窗同意主要人選 |
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
3. 今日重要消息。
4. 決策與承諾。
5. 待辦事項；分開保留可能說話者、明確指派的負責人、提出時間與期限。
6. 值得追蹤的想法或靈感。
7. 人名、專案名與產品名等關鍵實體。
8. 可能辨識錯誤或需要人工確認的片段。
9. 100 字內的今日摘要。

時間來自每日逐字稿的段落標題，而不是讓雲端模型猜測。例如原始資料：

```markdown
### 19:40:00–19:40:30 — 可能：家人二（87%）

明天記得去拿包裹，九點前要出門。
```

摘要會使用類似以下格式：

```markdown
## 事件時間軸

- 約 19:40｜可能說話者：家人二：提到明天要拿包裹，並希望九點前出門。

## 家庭成員重點（依可能說話者）

### 家人二

- 約 19:40：提醒明天拿包裹，並提到九點前出門。

## 待辦事項

- 約 19:40｜可能說話者：家人二：明天拿包裹；預計九點前出門。負責人需確認。
```

`19:40:00–19:40:30` 是 30 秒音訊片段的時間範圍，不代表事件精確發生在第一秒。摘要因此只顯示到分鐘並加上「約」；事件跨越相鄰片段時可顯示 `約 19:40–19:41`。無法對應來源段落的資訊必須標示「時間不明」，不可拿摘要執行時間代替，也不可從對話語意自行推測時間。

時間與人別規則都由程式固定附加到每一次 Codex 請求，包括長逐字稿的每個分段與最後整併；即使現有 `config.yaml` 使用舊版或自訂 `summary.prompt`，升級後也會生效。長逐字稿依 `### 時間 — 人別` 的完整段落切分，避免標題與內容被拆到不同請求。所有時間均沿用錄音 Mac 的本地日期與時區。

人別是本機聲音特徵的近似結果，不是已確認身分。摘要一律使用「可能說話者」措辭；同一事件跨多位成員時可列多位或標示「可能多人」，把握不足則保留「不確定／人別未提供」。說話者只代表該片段的可能主要聲音，不能直接推定是事件執行者或待辦負責人。

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

## 安裝常駐工作

務必先通過手動 `listen --once`，再安裝 listener：

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
- 在「家庭成員與人聲」編輯成員、查看註冊狀態、錄製／更新或刪除個別聲音樣本。
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
- 選單列 App 的 FamilyRecorder 麥克風權限紀錄。

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

系統會把 30 秒 chunk 切成數個短視窗，比較音色、頻譜與音高特徵；只有相似度、第一／第二名差距與多視窗一致性都達標才顯示姓名。多人同時說話、電視、距離過遠或把握不足時，會標「可能多人」或「不確定」。目前標的是整段的主要可能說話者，不是逐字逐句分離；錯認仍然可能發生，摘要也被要求不得把此標籤當成已確認事實。

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

## 常見問題

**找不到 XVF3800**：先在「系統資訊 → USB」與「音訊 MIDI 設定」確認裝置，再跑 `list-devices`。某些板子顯示 `XMOS XVF3800 Voice Processor`，不只 `XVF3800`。

**Invalid sample rate**：確認 YAML 目標為 16000。程式會在 16 kHz 開啟失敗時改用裝置宣告的 48 kHz，再於本機轉成 16 kHz；若裝置預設值不正確，先在「音訊 MIDI 設定」選 16 kHz 或 48 kHz。

**LaunchAgent 沒收到聲音**：先確定同一支已安裝的 runtime binary 能手動 `listen --once`；檢查「系統設定 → 隱私權與安全性 → 麥克風」與 `listener.error.log`。macOS 麥克風權限是每台機器的互動授權，安裝腳本不能替你繞過。

**一直被 VAD 略過**：查看 log 的 RMS 與 speech ratio，先以 `-55 dBFS`／`0.02` 測試，再逐步調嚴；也可用 placement test 比較實際位置。

**人別常顯示不確定／認錯人**：讓每位成員在相同麥克風位置重新錄製自然語音，避免電視、音樂與多人同時說話。若誤認多，提高 `min_similarity` 或 `min_margin`；若大多不確定，才小幅降低。這項功能不能用於門禁、付款、家長監護或任何需要確認身分的用途。

**聲音樣本一直建立失敗**：確認「系統設定 → 隱私權與安全性 → 麥克風」中的 FamilyRecorder 已開啟。選單列程式會在錄製樣本前主動檢查權限；未允許時不會開始一段必定失敗的錄音，並可直接打開對應的系統設定頁。

**Whisper 變慢或發熱**：把模型改成 `medium` 或 `small` 並更新 YAML；不要只增加 threads。確認安裝輸出包含 Metal，且 `doctor` 指向正確 build。

**摘要沒有執行**：先跑 `codex login status` 與相同的手動 `summary` 指令；再檢查逐字稿日期、網路與 `summary.error.log`。若登入失效，互動執行 `codex login`。排程預設在 00:10 整理「昨天」。

**摘要沒有事件時間**：確認已升級到 0.6.0 以上，再對同一天重新執行 `summary --date YYYY-MM-DD`。舊摘要檔不會自行重寫；新版在每次單段、分段與最終整併請求都會附加時間輸出規則，現有自訂 prompt 不需手動修改。

**摘要沒有保留人別**：確認已升級到 0.8.0 以上，並先檢查當日逐字稿標題是否真的有「可能：姓名／可能多人／不確定」。舊摘要不會自動重寫；重新整理指定日期後，新版會在事件時間軸、家庭成員重點、消息、決策、待辦與想法中盡可能保留可能說話者。若來源片段本身沒有人別，摘要不會自行猜測。

**選單列沒有圖示**：重跑 `./scripts/install_menubar.sh`，再檢查 `launchctl print "gui/$UID/com.familyrecorder.menubar"` 與 `menubar.error.log`。選單的「結束」是刻意正常退出，LaunchAgent 不會立即重開；重跑安裝腳本即可。

**解除安裝器顯示沒有找到安裝內容**：確認是以安裝 FamilyRecorder 的同一個 macOS 使用者登入。若只剩舊資料、選單列已損壞，可從最新版 DMG 直接打開「解除安裝 FamilyRecorder.app」。
