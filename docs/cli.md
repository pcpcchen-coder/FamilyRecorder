# CLI 指令參考

[English](cli.en.md) · **繁體中文** · [返回文件索引](README.md)

`family-recorder` 是整個系統唯一的進入點。選單列 App、LaunchAgent 與安裝腳本全都透過它操作系統，因此每一個圖形介面上的動作，都有對應的指令可用。

---

## 執行方式

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
FR="$RUNTIME/venv/bin/family-recorder"

"$FR" --config "$CONFIG" <指令> [參數]
```

### 全域參數

| 參數 | 預設 | 說明 |
|---|---|---|
| `--config PATH` | `~/.config/familyrecorder/config.yaml` | 設定檔位置 |
| `--verbose` | 關閉 | 詳細 log |

> 有一個別名 `xvf-listener` 指向同一個進入點。

---

## 診斷與狀態

| 指令 | 說明 |
|---|---|
| `list-devices` | 列出 macOS 音訊輸入裝置與其 ID、聲道數、預設取樣率 |
| `doctor` | 檢查設定與 runtime 相依：裝置選擇、whisper.cpp 路徑、模型、Codex 登入狀態、方向遙測 |
| `diagnose-beamforming` | **唯讀**驗證擷取的 UAC 聲道確實是 beamformed／processed |
| `probe-direction` | 取樣並顯示 XVF3800 方向遙測，不寫入逐字稿 |

```bash
"$FR" --config "$CONFIG" list-devices
"$FR" --config "$CONFIG" doctor
"$FR" --config "$CONFIG" diagnose-beamforming --json
"$FR" --config "$CONFIG" probe-direction --seconds 2
```

| 參數 | 適用指令 | 預設 | 說明 |
|---|---|---|---|
| `--json` | `diagnose-beamforming` | 關閉 | 輸出機器可讀的 JSON |
| `--seconds N` | `probe-direction` | `2.0` | 取樣秒數 |

---

## 錄音

| 指令 | 說明 |
|---|---|
| `listen` | 執行常駐 listener。正式使用由 LaunchAgent 呼叫 |
| `listen --once` | 只處理一個 chunk 後結束。**bring-up 驗收用** |
| `pause` | 暫停麥克風擷取 |
| `pause --minutes N` | 暫停 N 分鐘後自動恢復 |
| `resume` | 恢復擷取 |

```bash
"$FR" --config "$CONFIG" listen --once
"$FR" --config "$CONFIG" pause --minutes 60
"$FR" --config "$CONFIG" resume
```

暫停狀態寫入 `data_dir/control.json`，listener 每秒檢查一次，約 1 秒內關閉麥克風串流。**當下未完成的 chunk 會直接丟棄，不保存。**

> ⚠️ 正式 bring-up 請透過原生 App 身分執行，才會取得正確的 macOS 麥克風授權：
> ```bash
> /Applications/FamilyRecorder.app/Contents/MacOS/FamilyRecorder \
>   --service listener-once --program "$FR" --config "$CONFIG"
> ```

---

## 摘要

| 指令 | 說明 |
|---|---|
| `summary` | 整理 Mac 本地日期的**昨天**，與每日排程相同 |
| `summary --date YYYY-MM-DD` | 整理指定日期 |

```bash
"$FR" --config "$CONFIG" summary
"$FR" --config "$CONFIG" summary --date 2026-08-19
"$FR" --config "$CONFIG" summary --date "$(date +%F)"   # 整理今天
```

重跑同一天會**覆寫** `summaries/YYYY-MM-DD.md`，並更新 SQLite `summaries` 表的同一筆日期索引，不會建立多份互相衝突的摘要。

---

## 模型與提示

| 指令 | 說明 |
|---|---|
| `set-whisper-model --path PATH` | 切換到已下載的 whisper.cpp 模型 |
| `download-whisper-model --model NAME` | 下載、驗證並切換到多語模型 |
| `set-summary-model --model NAME` | 設定 Codex 摘要模型。空字串代表沿用帳號預設 |
| `set-summary-prompt --prompt TEXT` | 設定可編輯的摘要指示 |
| `reset-summary-prompt` | 恢復內建摘要指示 |
| `set-common-terms --term T [--term T ...]` | 設定改善本機辨識的姓名與術語 |

```bash
"$FR" --config "$CONFIG" download-whisper-model --model small-q5_1
"$FR" --config "$CONFIG" set-whisper-model --path "$RUNTIME/whisper.cpp/models/ggml-medium.bin"
"$FR" --config "$CONFIG" set-summary-model --model ""       # 回到帳號預設
"$FR" --config "$CONFIG" set-common-terms --term "陳樂融" --term "二次函數"
```

模型名稱經 allowlist 驗證，來源是 whisper.cpp 官方下載腳本指定的 Hugging Face repository。未完成的檔案以 `.partial` 保存供下次續傳，完成 GGML 格式驗證後才切換。**原有模型不會被刪除。**

`set-common-terms` 會**取代**整份清單，不是附加。切換模型或字詞後會重啟 listener。

---

## 防幻覺過濾

| 指令 | 說明 |
|---|---|
| `set-hallucination-preset --name {relaxed,balanced,strict}` | 套用三段預設之一 |
| `set-hallucination-filter [各項門檻]` | 逐項調整門檻 |

```bash
"$FR" --config "$CONFIG" set-hallucination-preset --name strict
"$FR" --config "$CONFIG" set-hallucination-filter \
  --min-avg-logprob -0.70 --repeat-window-seconds 600
```

`set-hallucination-filter` 只更新你明確指定的欄位，其他保持不變。可用參數與 YAML 欄位一一對應（底線改成連字號）：

**布林**（值為 `true`／`false`）：`--enabled`、`--hardware-silence-guard-enabled`、`--adaptive-noise-enabled`、`--low-frequency-filter-enabled`、`--whisper-confidence-enabled`、`--suppress-non-speech-tokens`、`--repeat-filter-enabled`

**整數**：`--noise-window-chunks`、`--noise-min-samples`、`--repeat-window-seconds`、`--max-repetitions`、`--min-repeat-text-chars`

**浮點數**：`--hardware-silence-max-ratio`、`--hardware-silence-max-software-speech-ratio`、`--hardware-silence-max-snr-db`、`--noise-margin-db`、`--low-frequency-min-ratio`、`--tonal-energy-min-ratio`、`--no-speech-probability-max`、`--min-avg-logprob`、`--low-probability-threshold`、`--max-low-probability-ratio`、`--max-compression-ratio`、`--repeat-similarity-threshold`

每個欄位的意義見 [設定參考](configuration.md#hallucination_filter)。

---

## 家庭成員與人聲

| 指令 | 說明 |
|---|---|
| `set-speakers --name N [--name N ...]` | 設定已知家庭成員（1–8 位） |
| `enroll-speaker --name N` | 錄製暫時樣本，只保存本機聲音特徵 |
| `delete-speaker-profile --name N` | 刪除一位成員的本機特徵檔 |

```bash
"$FR" --config "$CONFIG" set-speakers --name "我" --name "家人二" --name "家人三"
"$FR" --config "$CONFIG" pause
"$FR" --config "$CONFIG" enroll-speaker --name "我" --seconds 15
"$FR" --config "$CONFIG" resume
```

| 參數 | 預設 | 說明 |
|---|---:|---|
| `--seconds N` | `15` | 錄製秒數 |
| `--delay N` | `2.0` | 開始前的倒數秒數 |

> ⚠️ **`enroll-speaker` 執行前要先 `pause`**，否則麥克風被 listener 佔用。選單列會自動處理這件事。

註冊音訊只存在記憶體，產生特徵後即丟棄，**不會建立 WAV**。`set-speakers` 會取代整份名單。

---

## 方向

| 指令 | 說明 |
|---|---|
| `set-direction-enabled --enabled {true,false}` | 開關 XVF3800 方向遙測 |
| `calibrate-direction` | 把目前說話位置校準為房間正前方（0°） |
| `probe-direction` | 取樣並顯示方向遙測 |

```bash
"$FR" --config "$CONFIG" calibrate-direction --seconds 4
"$FR" --config "$CONFIG" set-direction-enabled --enabled false
```

| 參數 | 預設 | 說明 |
|---|---:|---|
| `--seconds N` | `4.0`（校準）／`2.0`（測試） | 取樣秒數 |

---

## Google Calendar

| 指令 | 說明 |
|---|---|
| `set-calendar-enabled --enabled {true,false}` | 開關候選事件擷取 |
| `set-calendar-auto-create --enabled {true,false}` | 一次同意後自動建立事件 |
| `set-calendar-default --calendar-id ID --calendar-name NAME` | 設定全家預設日曆 |
| `set-member-calendar --member M --calendar-id ID --enabled {true,false}` | 為一位成員綁定／解除綁定日曆 |
| `set-member-calendar-default --member M --calendar-id ID` | 指定該成員的回退日曆 |
| `calendar-event-created --id N [--external-id ID]` | 把候選標記為已建立 |
| `dismiss-calendar-event --id N` | 略過一筆待確認候選 |

```bash
"$FR" --config "$CONFIG" set-calendar-default \
  --calendar-id "abc@group.calendar.google.com" --calendar-name "家庭"
"$FR" --config "$CONFIG" set-member-calendar \
  --member "家人二" --calendar-id "xyz@gmail.com" --calendar-name "個人" --enabled true
"$FR" --config "$CONFIG" dismiss-calendar-event --id 42
```

`set-member-calendar` 的 `--calendar-name` 可省略。成員的回退日曆**必須是已綁定給該成員的日曆之一**，否則設定驗證會失敗。

`calendar-event-created` 與 `dismiss-calendar-event` 主要由選單列 App 在使用者確認後呼叫，一般不需手動使用。候選 ID 可從 SQLite 查得：

```sql
select id, title, starts_at, member_name from calendar_candidates where status='pending';
```

---

## 測試與維護

| 指令 | 說明 |
|---|---|
| `placement-test --positions A B C` | 比較多個麥克風位置 |
| `cleanup` | 立即套用設定的原始音訊 retention |

```bash
"$FR" --config "$CONFIG" placement-test --positions "茶几中央" "櫃子上" "Mac旁"
"$FR" --config "$CONFIG" placement-test --positions A B --seconds 10 --sentences-file ./s.txt
"$FR" --config "$CONFIG" cleanup
```

| 參數 | 預設 | 說明 |
|---|---|---|
| `--positions ...` | `A B C` | 位置名稱，可任意多個 |
| `--seconds N` | 由 `placement_test.recording_seconds_per_sentence` 決定 | 每句錄音秒數 |
| `--sentences-file PATH` | 內建 20 句 | 自訂固定句（UTF-8，每行一句） |

---

## 內部指令

| 指令 | 說明 |
|---|---|
| `menu-status` | 供選單列 App 讀取狀態的機器可讀輸出。**不是穩定的公開介面** |

---

## 相關文件

- [設定參考](configuration.md) —— 每個指令背後修改的 YAML 欄位
- [硬體與收音](hardware.md) —— 診斷與校準指令的完整說明
- [選單列與服務管理](menu-bar.md) —— 圖形介面對應的指令
- [常見問題](troubleshooting.md) —— 用這些指令排查問題
