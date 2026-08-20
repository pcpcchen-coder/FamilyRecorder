# 常見問題

[English](troubleshooting.en.md) · **繁體中文** · [返回文件索引](README.md)

依症狀查詢。所有指令都假設已設定這幾個變數：

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
APP="/Applications/FamilyRecorder.app"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
DB="$HOME/xvf3800-listener-data/listener.sqlite3"
FR="$RUNTIME/venv/bin/family-recorder"
```

---

## 目錄

**硬體與收音**
[找不到 XVF3800](#找不到-xvf3800) ·
[Invalid sample rate](#invalid-sample-rate) ·
[Beamforming 診斷不是 OK](#beamforming-診斷不是-ok) ·
[一直被 VAD 略過](#一直被-vad-略過) ·
[方向顯示無法讀取](#方向顯示無法讀取) ·
[方向和人所在位置不一致](#方向和人所在位置不一致)

**權限與服務**
[LaunchAgent 沒收到聲音](#launchagent-沒收到聲音) ·
[麥克風 App 列表沒有 FamilyRecorder](#麥克風-app-列表沒有-familyrecorder) ·
[Google Calendar 沒有出現授權視窗](#按連接選擇預設-google-calendar-沒有出現授權視窗) ·
[系統設定仍顯示 python3.12](#系統設定仍顯示-python312-或-family-recorder) ·
[選單列沒有圖示](#選單列沒有圖示)

**辨識品質**
[安靜時一直出現相同字幕](#安靜時一直出現相同字幕人名) ·
[人別常顯示不確定／認錯人](#人別常顯示不確定認錯人) ·
[聲音樣本一直建立失敗](#聲音樣本一直建立失敗) ·
[Whisper 變慢或發熱](#whisper-變慢或發熱)

**摘要與行事曆**
[摘要沒有執行](#摘要沒有執行) ·
[摘要沒有事件時間](#摘要沒有事件時間) ·
[摘要沒有保留人別](#摘要沒有保留人別) ·
[摘要沒有方向資訊](#摘要沒有方向資訊) ·
[待確認事件是空的](#摘要有日期事件但待確認事件是空的)

**解除安裝**
[解除安裝器顯示沒有找到安裝內容](#解除安裝器顯示沒有找到安裝內容)

---

## 硬體與收音

### 找不到 XVF3800

先在「**系統資訊 → USB**」與「**音訊 MIDI 設定**」確認裝置存在，再跑：

```bash
"$FR" --config "$CONFIG" list-devices
```

某些板子顯示 `XMOS XVF3800 Voice Processor`，而不只是 `XVF3800`。找不到時在 YAML 明確指定：

```yaml
audio:
  device_id: 2
  # 或
  device_name_contains: "XMOS XVF3800 Voice Processor"
```

---

### Invalid sample rate

確認 YAML 目標為 `16000`。程式會在 16 kHz 開啟失敗時改用裝置宣告的 48 kHz，再於本機轉成 16 kHz。

若裝置預設值不正確，先在「**音訊 MIDI 設定**」把裝置選成 16 kHz 或 48 kHz。

---

### Beamforming 診斷不是 OK

1. **先確認 `audio.channels: 1`。** 設成 `2` 會被判為左右混合，無法驗證。
2. 執行 `diagnose-beamforming --json` 檢查左聲道 routing：

```bash
"$FR" --config "$CONFIG" diagnose-beamforming --json
```

category `1/2/3/11` 是 raw／intermediate microphone，**不應用於目前的 FamilyRecorder**。診斷只讀不改設定；如果 routing 被其他工具改動過，請依 XVF3800 韌體文件恢復 processed auto-selected beam。

完整判讀表見 [硬體與收音](hardware.md#怎麼判讀結果)。

---

### 一直被 VAD 略過

先看實際被哪一關擋下：

```bash
sqlite3 "$DB" "select started_at, round(rms_dbfs,1) rms, round(snr_db,1) snr,
  round(software_speech_ratio,2) sw, round(hardware_speech_ratio,2) hw, gate_reason
  from captures order by id desc limit 20;"
```

| `gate_reason` | 代表 | 怎麼處理 |
|---|---|---|
| `silence` | software 與硬體都判安靜 | 調低 `vad.min_rms_dbfs` 與 `min_speech_ratio` |
| `software_vad; speech_energy_unavailable` | 硬體遙測讀不到 | 見 [方向顯示無法讀取](#方向顯示無法讀取) |
| `hallucination_filter:*` | 防幻覺攔下 | 改成「寬鬆」預設 |

先以 software VAD 的 `-55 dBFS` / `0.02` 測試確認整條路徑會動，再逐步調嚴：

```yaml
vad:
  min_rms_dbfs: -55.0
  min_speech_ratio: 0.02
```

也可以用 [placement test](hardware.md#mic-placement-test) 比較實際位置的收音品質。

> 若 Speech Energy 永遠是 `0`，先跑 `doctor` 並**對麥克風持續自然說話**。不要把系統喇叭的回音當成可靠的近端測試。

---

### 方向顯示無法讀取

1. 確認是 VID `0x2886` / PID `0x001A` 的 reSpeaker XVF3800。
2. 安裝 libusb：`brew install libusb`
3. 從選單執行「**檢查系統狀態**」，或 `"$FR" --config "$CONFIG" doctor`。

> **音訊仍可錄到，不代表 USB vendor control 一定可讀。** 這是兩條獨立通道。FamilyRecorder 會保留錄音並把方向標成無法讀取，**不會**讓 listener 因方向功能停止。

---

### 方向和人所在位置不一致

1. 確認麥克風**沒有旋轉**。
2. 重新執行「**把目前位置校準為正前方**」：

```bash
"$FR" --config "$CONFIG" calibrate-direction --seconds 4
```

牆面反射、電視、喇叭回音、多人同時說話，或兩人位於相同方位，都可能干擾 DoA。**方向是輔助線索，不是人別或距離感測器。**

---

## 權限與服務

### LaunchAgent 沒收到聲音

1. 先用第一次 bring-up 的指令測試：

```bash
"$APP/Contents/MacOS/FamilyRecorder" \
  --service listener-once --program "$FR" --config "$CONFIG"
```

2. 檢查「**系統設定 → 隱私權與安全性 → 麥克風**」中 `FamilyRecorder.app` 已開啟。
3. 看錯誤 log：

```bash
tail -50 "$HOME/xvf3800-listener-data/logs/listener.error.log"
```

> macOS 麥克風權限是**每台機器的互動授權**，安裝腳本不能替你繞過。

---

### 麥克風 App 列表沒有 FamilyRecorder

升級至 **0.14.3 或更新版本**，並重跑：

```bash
./scripts/install_menubar.sh
./scripts/install_launchd.sh
```

新版把主 App 安裝到標準的 `/Applications/FamilyRecorder.app`、包含 Hardened Runtime 所需的 **Audio Input entitlement**，並自動移除舊版位於 Application Support 或 `~/Applications` 的重複 App。

首次啟動按下 macOS 的「允許」後，**完整重開系統設定**即可看到 `FamilyRecorder.app`。模型、逐字稿與錄音資料不會因遷移而移動。

---

### 按「連接／選擇預設 Google Calendar」沒有出現授權視窗

升級至 **0.14.4 或更新版本**。

0.14.3 的 Hardened Runtime 簽章遺漏 Calendar entitlement，macOS 會在顯示授權視窗**之前**就拒絕請求。0.14.4 補齊 entitlement，且選單會把「已設定但失去系統權限」的狀態顯示為「**需要重新授權**」。

Google 帳號、既有事件與 FamilyRecorder 的日曆對應設定**不會被刪除**。

---

### 系統設定仍顯示 `python3.12` 或 `family-recorder`

這是 0.8.0 以前直接啟動 Python worker 留下的**歷史項目**。

1. 確認已升級到 0.9.0 以上。
2. 重跑 `install_menubar.sh`、`install_launchd.sh` 與 `install_daily_summary.sh`。
3. 把舊項目的切換鈕關閉。

目前使用中的麥克風項目應是 `FamilyRecorder.app`，背景工作則顯示 `FamilyRecorder`。

> ⚠️ **不要為了清掉一列歷史紀錄而重設所有 App 的麥克風權限。**

---

### 選單列沒有圖示

```bash
./scripts/install_menubar.sh
launchctl print "gui/$UID/com.familyrecorder.menubar"
tail -50 "$HOME/xvf3800-listener-data/logs/menubar.error.log"
```

> 選單的「結束」是**刻意的正常退出**，LaunchAgent 不會立即重開。重跑安裝腳本或重新登入即可。

---

## 辨識品質

### 安靜時一直出現相同字幕／人名

這通常是 Whisper 對低資訊底噪產生的**固定幻覺**，不代表模型被植入。

1. 確認選單「**防幻覺過濾**」已開啟並使用「**平衡**」。
2. 查看今日攔截數與原因：

```bash
sqlite3 "$DB" "select reason, count(*) from transcription_audits
  where decision='filtered' and date(started_at)=date('now','localtime')
  group by reason order by 2 desc;"
```

3. 若仍漏過，改成「**嚴格**」；若短而輕聲的真實談話被略過，改成「**寬鬆**」，再以進階門檻微調。

> ⚠️ **不要只把某一句加入黑名單。** 幻覺文字會隨模型與提示改變，黑名單很快就失效 —— 這也是本專案不提供句子黑名單的原因。

---

### 人別常顯示不確定／認錯人

**先改善樣本，再改門檻。**

1. 讓每位成員在**相同麥克風位置**重新錄製自然語音。
2. 避免電視、音樂與多人同時說話。
3. 兒童聲音隨成長變化，建議定期更新樣本。

改門檻：

| 症狀 | 調整 |
|---|---|
| 誤認多 | 提高 `speakers.min_similarity` 或 `min_margin` |
| 大多不確定 | **小幅**降低 `min_similarity` |

> ⚠️ 這項功能**不能**用於門禁、付款、家長監護或任何需要確認身分的用途。

---

### 聲音樣本一直建立失敗

確認「**系統設定 → 隱私權與安全性 → 麥克風**」中的 FamilyRecorder 已開啟。

選單列程式會在錄製樣本前**主動檢查權限**；未允許時不會開始一段必定失敗的錄音，並可直接打開對應的系統設定頁。

從指令列註冊時，記得**先暫停 listener**：

```bash
"$FR" --config "$CONFIG" pause
"$FR" --config "$CONFIG" enroll-speaker --name "我" --seconds 15
"$FR" --config "$CONFIG" resume
```

---

### Whisper 變慢或發熱

把模型改成 `medium` 或 `small`，**不要只增加 threads**：

```bash
"$FR" --config "$CONFIG" download-whisper-model --model medium
```

確認安裝輸出包含 **Metal**，且 `doctor` 指向正確的 build。

---

## 摘要與行事曆

### 摘要沒有執行

1. 檢查登入：

```bash
codex login status
```

2. 手動跑同一天：

```bash
"$FR" --config "$CONFIG" summary --date 2026-08-19
```

3. 檢查逐字稿日期是否真的有內容、網路是否可用，以及：

```bash
tail -50 "$HOME/xvf3800-listener-data/logs/summary.error.log"
```

若登入失效，互動執行 `codex login`。

> 排程**預設在 00:10 整理「昨天」**。想要今天的摘要，用選單列的「立即整理今天」，或 `summary --date "$(date +%F)"`。

---

### 摘要沒有事件時間

1. 確認已升級到 **0.6.0 以上**。
2. 對同一天重新執行 `summary --date YYYY-MM-DD`。

**舊摘要檔不會自行重寫。** 新版在每次單段、分段與最終整併請求都會附加時間輸出規則，現有自訂 prompt 不需手動修改。

---

### 摘要沒有保留人別

1. 確認已升級到 **0.8.0 以上**。
2. 先檢查當日逐字稿標題是否**真的有**「可能：姓名／可能多人／不確定」。
3. 重新整理指定日期。

若來源片段本身沒有人別，**摘要不會自行猜測** —— 這是刻意的。

---

### 摘要沒有方向資訊

方向功能**只會影響升級後新產生的逐字稿片段**。

1. 確認逐字稿標題含「方向：…」。
2. 重新整理指定日期。

0.10.0 起會要求每次分段與最終摘要保留來源方向，並新增「對話方向與人別線索」段落。

---

### 摘要有日期／事件，但「待確認事件」是空的

1. 確認已升級到 **0.11.1 以上**。
2. 重新執行同一天摘要。

新版會在摘要完成後以**獨立的結構化 ChatGPT 請求**擷取行事曆候選。只有日期而沒有時間的事件會列為**全天候選**；日期無法解析的會被略過。

摘要檔底部會明確顯示：找到的候選數量、沒有找到，或擷取失敗警告。

```bash
sqlite3 "$DB" "select id, summary_date, title, starts_at, status
  from calendar_candidates order by id desc limit 20;"
```

> 0.12.0 起也可一次同意「摘要後自動加入」。此模式成功時待確認清單會**很快歸零** —— 請直接到 Google Calendar 檢查事件。

---

## 解除安裝

### 解除安裝器顯示沒有找到安裝內容

確認是以**安裝 FamilyRecorder 的同一個 macOS 使用者**登入。

若只剩舊資料、選單列已損壞，可從最新版 DMG 直接打開「**解除安裝 FamilyRecorder.app**」。

或從原始碼 checkout：

```bash
./scripts/uninstall_family_recorder.sh inspect
```

---

## 還是沒解決？

1. 跑一次完整體檢並附上輸出：

```bash
"$FR" --config "$CONFIG" doctor
```

2. 收集相關 log：

```bash
tail -100 "$HOME/xvf3800-listener-data/logs/listener.error.log"
```

3. 到 [GitHub Issues](https://github.com/pcpcchen-coder/FamilyRecorder/issues) 開一個 issue。

> ⚠️ **貼上前請先移除逐字稿內容、家庭成員姓名與檔案路徑中的使用者名稱。**

---

## 相關文件

- [設定參考](configuration.md) —— 每個參數的意義
- [硬體與收音](hardware.md) —— 診斷指令
- [資料與 SQLite](data-model.md#常用查詢) —— 更多診斷查詢
- [開發與測試 → 驗收清單](development.md#驗收清單) —— 31 項實機檢查
