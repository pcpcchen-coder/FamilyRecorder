# 設定參考

[English](configuration.en.md) · **繁體中文** · [返回文件索引](README.md)

設定檔位置：`~/.config/familyrecorder/config.yaml`
完整範例：[`config.example.yaml`](../config.example.yaml)

安裝腳本**只在檔案不存在時**建立設定，永遠不會覆蓋既有內容。大部分欄位也可以從選單列以圖形介面調整，而且會保留 YAML 中無關的註解與值。

---

## 目錄

- [audio](#audio) · [vad](#vad) · [whisper](#whisper) · [hallucination_filter](#hallucination_filter)
- [storage](#storage) · [speakers](#speakers) · [direction](#direction)
- [calendar](#calendar) · [summary](#summary) · [placement_test](#placement_test)
- [改設定之後要重啟嗎](#改設定之後要重啟嗎)

---

## `audio`

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `device_name_contains` | `"XVF3800"` | 裝置名稱比對字串，不分大小寫。找不到這個字串時，還會對 `XVF3800`、`XMOS`、`USB`、`array` 評分 |
| `device_id` | `null` | 直接指定 PortAudio 裝置 ID。設了就優先於名稱比對 |
| `allow_default_input` | `false` | 找不到 XVF／XMOS／USB 裝置時，是否允許改用系統預設（通常是內建麥克風）。**預設不允許**，避免悄悄改錄內建麥克風 |
| `sample_rate` | `16000` | 目標取樣率。若裝置不支援，會用裝置預設值擷取再本機轉換 |
| `channels` | `1` | **建議保持 `1`**。設 `2` 會把左右聲道 downmix，破壞 beamformed 訊號，且 `diagnose-beamforming` 會標示 `ambiguous_stereo_downmix` |
| `chunk_seconds` | `30` | 連續錄音的 chunk 長度 |
| `retry_seconds` | `10` | 裝置拔線或暫時不可用時的重試間隔 |

---

## `vad`

第一層語音判定。**這一層只決定「要不要留下這個 chunk」，不決定文字內容。**

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `enabled` | `true` | 關閉後所有 chunk 都會被保留並送進 Whisper，磁碟用量與運算量都會大增 |
| `aggressiveness` | `2` | WebRTC VAD 強度。`0` 最寬鬆、`3` 最嚴格 |
| `frame_ms` | `30` | VAD 分析 frame 長度，可為 10／20／30 |
| `min_speech_ratio` | `0.08` | 一個 chunk 至少要有多少比例的 frame 被判為語音 |
| `min_rms_dbfs` | `-48.0` | 音量 gate。**越接近 0 越嚴格**；`-55` 比 `-48` 寬鬆 |

**調校方向：**

| 症狀 | 怎麼調 |
|---|---|
| 真實對話一直被略過 | 調低 `min_speech_ratio`（例如 `0.04`）與 `min_rms_dbfs`（例如 `-54`） |
| 環境雜訊一直被錄下來 | 調高兩者，或提高 `aggressiveness` |
| 只想抓近距離說話 | 調高 `min_rms_dbfs`（例如 `-40`） |

先用 `-55` / `0.02` 確認硬體路徑會動，再逐步收緊。觀察 `captures.gate_reason` 判斷實際被哪一關擋下。

---

## `whisper`

| 欄位 | 預設 | 說明 |
|---|---|---|
| `binary_path` | `…/whisper.cpp/build/bin/whisper-cli` | whisper.cpp 執行檔 |
| `model_path` | `…/models/ggml-large-v3-turbo.bin` | 本機模型。可由選單列切換 |
| `language` | `"zh"` | Whisper 語言代碼 |
| `threads` | `8` | 解碼執行緒。變慢或發熱時應該**換小模型**，不是只加 threads |
| `initial_prompt` | 繁中家庭對話提示 | 本機 Whisper 的引導提示 |
| `common_terms` | `[]` | 姓名與專有名詞清單。會加入本機提示；辨識後也會對「3 字以上、只差一個字」的無歧義近似結果做保守校正 |
| `extra_args` | `[]` | 額外傳給 `whisper-cli` 的參數 |

`common_terms` 只在本機使用，不會送到雲端。可從選單列「常用字詞校正」逐行維護。

---

## `hallucination_filter`

多層防幻覺。**沒有任何規則會封鎖特定句子** —— 幻覺文字會隨模型與提示改變，黑名單很快失效，因此判定依據是統計特徵。

判定順序見 [系統架構](architecture.md#辨識路徑whisper-與文字防幻覺)。

### 三段預設

選單列「防幻覺過濾」提供三個預設。差異如下（未列出的欄位三者相同）：

| 欄位 | 寬鬆 relaxed | 平衡 balanced（預設） | 嚴格 strict |
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

**寬鬆**：怕漏掉真實但輕聲的對話（例如夢境記錄）。
**平衡**：一般家庭使用。
**嚴格**：安靜房間、固定底噪，一直出現重複幻覺字幕時。

### 完整欄位

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `enabled` | `true` | 關閉後只剩基本 VAD gate |
| **聲學層** | | |
| `hardware_silence_guard_enabled` | `true` | 允許硬體靜音否決 software VAD 誤判 |
| `hardware_silence_max_ratio` | `0.01` | Speech Energy 不高於此比例視為硬體靜音 |
| `hardware_silence_max_software_speech_ratio` | `0.30` | 硬體靜音時，software VAD 低於此值才算弱證據 |
| `hardware_silence_max_snr_db` | `10.0` | 硬體靜音時 SNR 也不高於此值才否決，避免單一感測器造成漏字 |
| `adaptive_noise_enabled` | `true` | 啟用滾動中位數噪音基線 |
| `noise_window_chunks` | `120` | 基線的歷史視窗長度 |
| `noise_min_samples` | `4` | 基線生效前的最少樣本數 |
| `noise_margin_db` | `3.0` | 目前音量在基線多少 dB 內仍視為近似底噪 |
| `low_frequency_filter_enabled` | `true` | 啟用低頻／窄頻固定音判定 |
| `low_frequency_min_ratio` | `0.65` | 80–300 Hz 低頻能量比例門檻 |
| `tonal_energy_min_ratio` | `0.35` | 少數固定頻率占總能量比例的門檻 |
| **Whisper 文字層** | | |
| `whisper_confidence_enabled` | `true` | 啟用 token 信心相關判定 |
| `no_speech_probability_max` | `0.60` | 無語音機率的拒絕門檻，也會傳給 whisper.cpp decoder |
| `min_avg_logprob` | `-0.80` | 平均 token log probability 下限。**越接近 0 越嚴格** |
| `low_probability_threshold` | `0.15` | 單一 token 被視為低可信的機率界線 |
| `max_low_probability_ratio` | `0.15` | 一段文字最多可有多少比例的低可信 token |
| `max_compression_ratio` | `2.40` | 過度重複文字的壓縮率上限 |
| `suppress_non_speech_tokens` | `true` | 抑制非語音 token |
| **跨片段層** | | |
| `repeat_filter_enabled` | `true` | 啟用跨 chunk 重複長句過濾 |
| `repeat_window_seconds` | `300` | 回看多久之內的歷史文字 |
| `max_repetitions` | `1` | 視窗內允許相同／近似長句先出現幾次 |
| `repeat_similarity_threshold` | `0.96` | 正規化文字相似度達此比例視為重複 |
| `min_repeat_text_chars` | `5` | 只有至少這麼長的文字才做重複過濾，因此「好」「嗯」不受影響 |

所有攔截決策都寫入 SQLite 的 `transcription_audits`，包含原始候選文字與原因。

---

## `storage`

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `data_dir` | `~/xvf3800-listener-data` | 所有資料的根目錄。新目錄會建立 `.familyrecorder-data` 所有權標記 |
| `keep_audio_days` | `7` | WAV 保留天數。`0` 代表只保留尚未超過當下 cutoff 的檔案 |
| `delete_audio_after_transcription` | `false` | 成功或空白轉錄後立即刪 WAV。**失敗的 WAV 一律保留**供排查 |

手動執行 retention：

```bash
family-recorder --config "$CONFIG" cleanup
```

Retention 只影響 `audio/`。逐字稿、摘要、SQLite 遙測與稽核記錄不受影響。

---

## `speakers`

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `enabled` | `false` | 有家庭成員時由選單自動開啟 |
| `members` | `[]` | 已知成員姓名，1–8 位 |
| `min_similarity` | `0.82` | 最低特徵相似度。**提高可減少誤認，但增加「不確定」** |
| `min_margin` | `0.025` | 第一名至少要比第二名高出的差距 |
| `dominance_threshold` | `0.65` | 一個片段內必須有多少比例的分析視窗同意主要人選 |

姓名只寫進這台 Mac 的私人 YAML，不必進公開 repo。詳見 [家庭成員與方向](speakers.md)。

---

## `direction`

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `enabled` | `true` | 同步讀取 XVF3800 方向遙測。讀取失敗時錄音仍繼續 |
| `sample_interval_seconds` | `0.25` | 取樣間隔，預設每秒 4 次 |
| `front_angle_degrees` | `0.0` | 哪個原始角度代表房間正前方。**建議由選單校準**而非手填 |
| `min_speech_samples` | `3` | 一個文字片段至少需要幾個帶語音旗標的方向樣本 |
| `cluster_tolerance_degrees` | `35.0` | 相近方向合併的容許角度 |
| `multiple_direction_min_ratio` | `0.25` | 第二方向至少佔多少語音樣本才標示為多方向 |
| `speech_energy_enabled` | `true` | 讀取四束 Speech Energy 並與 software VAD 融合 |
| `speech_energy_min_ratio` | `0.08` | auto-selected beam 在一個 chunk 中非零樣本的最低比例 |
| `speech_energy_min_rms_dbfs` | `-55.0` | 硬體判為語音時**仍須達到**的本機 RMS 安全下限 |
| `speech_energy_threshold` | `0.0` | 大於此值視為硬體語音。官方定義預設為非零即可能有語音 |
| `usb_timeout_ms` | `1000` | USB control 逾時 |

詳見 [硬體與收音](hardware.md)。

---

## `calendar`

| 欄位 | 預設 | 說明 |
|---|---|---|
| `provider` | `"google"` | 目前唯一支援的 provider |
| `enabled` | `false` | 選定預設日曆後由選單自動開啟 |
| `auto_create` | `false` | **需要一次明確同意**。開啟後摘要產生的候選會自動寫入日曆，可隨時關閉 |
| `default_calendar_id` | `""` | 全家事件或無法判斷成員時使用的預設日曆 |
| `default_calendar_name` | `""` | 上者的顯示名稱 |
| `calendar_names` | `{}` | 日曆 ID 到顯示名稱的對應 |
| `member_calendar_ids` | `{}` | 每位成員可使用的多個日曆 |
| `member_default_calendar_ids` | `{}` | 每位成員在無法精確分類時的回退日曆。**必須是該成員已綁定的日曆之一** |

FamilyRecorder **不另存 Google 密碼或 OAuth token**；它透過已加入 macOS「Internet 帳號」並在「行事曆」App 中同步的 Google 帳號寫入。詳見 [每日摘要與行事曆](daily-summary.md#google-calendar-候選事件)。

---

## `summary`

| 欄位 | 預設 | 說明 |
|---|---|---|
| `enabled` | `true` | 設 `false` 可完全停用雲端摘要，只保留本機逐字稿 |
| `provider` | `"codex"` | 目前唯一支援的 provider |
| `model` | `""` | 空字串代表沿用 ChatGPT 帳號目前可用的 Codex 預設模型。填值才固定模型 |
| `codex_binary_path` | `"codex"` | 會搜尋 PATH、ChatGPT.app 與常見 Homebrew 位置 |
| `timeout_seconds` | `900` | 每次 Codex 摘要最長等待秒數 |
| `hour` / `minute` | `0` / `10` | LaunchAgent 每日執行時間。**修改後要重跑 `install_daily_summary.sh`** |
| `max_input_chars` | `300000` | 超過時切成多段摘要，再做一次最終去重整併 |
| `prompt` | 內建繁中格式 | 可自訂摘要重點。**安全規則、時間／人別／方向契約仍由程式強制附加** |

> **重要：** 排程執行整理的是**昨天**。想整理今天，請用選單列的「立即整理今天」，或手動執行 `summary --date $(date +%F)`。

`summary.prompt` 可從選單列「更換模型 → ChatGPT 摘要」以多行編輯器修改，或一鍵恢復內建格式。變更只套用到之後產生或重新執行的摘要。

---

## `placement_test`

| 欄位 | 預設 | 說明 |
|---|---:|---|
| `recording_seconds_per_sentence` | `8` | 每句錄音秒數 |
| `sentences_file` | `""` | 自訂固定句檔（UTF-8，每行一句）。留空使用內建 20 句 |

詳見 [硬體與收音 → Mic placement test](hardware.md#mic-placement-test)。

---

## 改設定之後要重啟嗎

| 改了什麼 | 需要做什麼 |
|---|---|
| `audio.*`、`vad.*`、`whisper.*`、`hallucination_filter.*`、`speakers.*`、`direction.*` | **重啟 listener**。從選單列「重新啟動錄音服務」，或 `launchctl kickstart -k "gui/$UID/com.familyrecorder.listener"` |
| `summary.model`、`summary.prompt` | 不用重啟。每次摘要執行時重新讀取 |
| `summary.hour` / `summary.minute` | **重跑 `./scripts/install_daily_summary.sh`**，plist 才會更新 |
| `storage.keep_audio_days` | 下次 retention 執行時生效，或立刻 `cleanup` |
| `calendar.*` | 不用重啟。選單列程式會讀取最新設定 |

從選單列做的變更會自動處理上述重啟。**只有手動編輯 YAML 時才需要自己重啟。**

---

## 相關文件

- [系統架構](architecture.md) —— 每個參數在哪一個決策點生效
- [硬體與收音](hardware.md) —— 收音相關參數的實測方法
- [常見問題](troubleshooting.md) —— 症狀導向的調校建議
- [應用場景指南](use-cases.md) —— 不同場景的建議設定組合
