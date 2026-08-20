# 安裝與上手

[English](getting-started.en.md) · **繁體中文** · [返回文件索引](README.md)

從零到「今天早上有一份摘要」。全程約 30–60 分鐘，其中大部分是等待 whisper.cpp 編譯與模型下載。

---

## 目錄

- [系統需求](#系統需求)
- [方式一：DMG 圖形安裝](#方式一dmg-圖形安裝建議)
- [方式二：從原始碼安裝](#方式二從原始碼安裝)
- [macOS 中看到的名稱](#macos-中看到的名稱)
- [第一次硬體 bring-up](#第一次硬體-bring-up)
- [安裝常駐工作](#安裝常駐工作)
- [下一步](#下一步)

---

## 系統需求

| 項目 | 需求 |
|---|---|
| 電腦 | Apple Silicon Mac（`arm64`） |
| 系統 | macOS 13 或更新版本 |
| 麥克風 | [reSpeaker XVF3800 USB 4-Mic Array](https://github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY)，VID `0x2886` / PID `0x001A` |
| 套件管理 | [Homebrew](https://brew.sh/) |
| 相依套件 | Homebrew `libusb`（安裝器會自動裝） |
| 磁碟 | 程式、模型與 build 約 2–4 GB；錄音資料另計 |
| 網路 | 只有雲端摘要需要。監聽、VAD、轉錄全程離線 |
| 帳號 | 想用每日摘要的話，需要可使用 Codex 的 ChatGPT 帳號。**不需要 API key** |

**錄音容量估算：** 16 kHz mono PCM16 在「持續有語音」的極端情況約 **2.8 GB／日**。實際使用因為安靜片段不落 WAV，通常遠低於此。預設 `keep_audio_days: 7`。

---

## 方式一：DMG 圖形安裝（建議）

從 [GitHub Releases](https://github.com/pcpcchen-coder/FamilyRecorder/releases) 下載最新的 `FamilyRecorder-*-arm64.dmg` 與對應的 `.sha256`。

**先核對 SHA-256：**

```bash
shasum -a 256 ~/Downloads/FamilyRecorder-*-arm64.dmg
cat ~/Downloads/FamilyRecorder-*-arm64.dmg.sha256
```

兩者相符後開啟 DMG：

1. 執行「**安裝 FamilyRecorder.app**」。
2. 選擇本機 Whisper 模型：`small`、`medium`，或建議的 `large-v3-turbo`。
3. 若尚未安裝 Codex，按「**安裝官方 Codex CLI**」；再按「**登入 ChatGPT**」，瀏覽器會開啟官方登入頁。
4. 按「**安裝 FamilyRecorder**」。安裝器會從 DMG 內的 wheel 安裝本程式、以 Metal 編譯 whisper.cpp、下載選定模型，並建立 listener／summary／選單列三個工作。
5. 接上 XVF3800，依 macOS 提示允許「FamilyRecorder」使用麥克風。

同一個 DMG 也附有「**解除安裝 FamilyRecorder.app**」。平常可直接從選單列波形圖示選「解除安裝 FamilyRecorder…」；若選單列無法啟動，重新掛載 DMG 後打開解除安裝器即可，不需要使用終端機。

### 關於登入

安裝器**不會**要求 OpenAI API key，也不會讀取 Codex 登入檔或 token；它只執行官方 `codex login` 與 `codex login status`。若一般瀏覽器返回流程受網路環境影響，可按「**改用裝置碼登入**」。

登入也可以稍後完成 —— 這時錄音與本機轉錄仍會安裝，但每日摘要排程要在登入後**重跑一次安裝器**才會啟用。

### 關於 Gatekeeper

目前公開 DMG 為 Apple Silicon、macOS 13+，使用 ad-hoc 簽署，**尚未經 Apple Developer ID 公證**。第一次開啟若被 Gatekeeper 阻擋，請在 Finder 對安裝 app 按右鍵 →「**打開**」，並確認下載來源與 SHA-256 無誤。

Homebrew 套件、whisper.cpp 原始碼／模型與 Codex CLI 仍需連線至其官方來源下載；FamilyRecorder 的 wheel 與安裝介面本身包含在 DMG 內。

---

## 方式二：從原始碼安裝

```bash
git clone https://github.com/pcpcchen-coder/FamilyRecorder.git
cd FamilyRecorder
./scripts/install_mac.sh
```

腳本會依序：

1. 安裝 Python 3.12、PortAudio、CMake、Git。
2. 建立 `~/Library/Application Support/FamilyRecorder/venv`。
3. 安裝 FamilyRecorder。
4. checkout `whisper.cpp` v1.8.1，以 `GGML_METAL=ON` 編譯。
5. 下載 `ggml-large-v3-turbo.bin`。
6. **僅在不存在時**建立 `~/.config/familyrecorder/config.yaml`，不覆蓋舊設定。
7. 偵測官方 Codex CLI／ChatGPT app，並顯示目前的 ChatGPT 登入狀態。

想先用較小模型測試：

```bash
WHISPER_MODEL=medium ./scripts/install_mac.sh
```

安裝腳本會下載並自動把 YAML 的 `whisper.model_path` 切到 `ggml-medium.bin`；原有 config 的其餘設定會保留。

### 再安裝選單列程式

**在做硬體驗收之前**，先安裝選單列：

```bash
./scripts/install_menubar.sh
```

它會用 Mac 內建的 Swift 工具編譯原生 `FamilyRecorder.app` 與「解除安裝 FamilyRecorder.app」。主 App 安裝到標準的 `/Applications/FamilyRecorder.app`；Python runtime、Whisper 模型與解除安裝器保留在 `~/Library/Application Support/FamilyRecorder`。

安裝器會先以**等同 Finder 雙擊的方式**開啟主 App，直接顯示 macOS 原生麥克風授權提示；按「允許」後才會啟動 listener。之後也可直接從「應用程式」打開 FamilyRecorder。

三個內部工作都關聯到 `/Applications` 裡的**同一個 App**，避免隱藏或使用者層級路徑造成 Spotlight／TCC 身分快取不一致。

---

## macOS 中看到的名稱

從 0.9.0 起，正式安裝後的所有使用者可見名稱統一如下：

| macOS 畫面 | 顯示名稱 |
|---|---|
| 系統設定 → 隱私權與安全性 → 麥克風 | `FamilyRecorder.app`（macOS 在此頁自動顯示 `.app` 副檔名） |
| 系統設定 → 一般 → 登入項目與延伸功能 → App 背景活動 | `FamilyRecorder`（三個背景工作合併在同一 App 下） |
| 選單列、通知與麥克風授權提示 | `FamilyRecorder` |

`com.familyrecorder.listener`、`com.familyrecorder.summary`、`com.familyrecorder.menubar` 只是 log 或診斷指令中使用的**內部識別碼**，不是 macOS 顯示給一般使用者的 App 名稱。

> **從 0.8.0 或更舊版本原地升級？** 舊的 `python3.12`／`family-recorder` 可能留在系統的歷史清單；可將它關閉，不需要刪除整個清單。新版錄音服務不再依賴該權限，而是由 `FamilyRecorder.app` 持有麥克風授權。

---

## 第一次硬體 bring-up

先接上 XVF3800，再依序執行。以下所有指令都會用到這三個變數：

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
APP="/Applications/FamilyRecorder.app"
CONFIG="$HOME/.config/familyrecorder/config.yaml"
```

### 步驟 1：列出裝置

```bash
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
  # 或
  device_name_contains: "XMOS XVF3800 Voice Processor"
```

### 步驟 2：總體檢

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" doctor
```

### 步驟 3：確認抓到正確的聲道

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" diagnose-beamforming
```

標準輸出應顯示左聲道 `(8, 0)` user-chosen／processed auto-selected beam（或 `(6, 3)` processed auto-selected beam），最後一行為：

```text
[OK] FamilyRecorder is capturing the beamformed/processed left UAC channel.
```

右聲道通常是 `(7, 3)` ASR/AEC residual。FamilyRecorder 預設 `audio.channels: 1`，因此只取第一個／左聲道，不把兩種不同處理目的的聲道平均混合。**診斷器不會改寫 XVF3800 routing。**

詳細說明見 [硬體與收音](hardware.md)。

### 步驟 4：授權麥克風，跑一個 30 秒 chunk

到「系統設定 → 隱私權與安全性 → 麥克風」允許 `FamilyRecorder`，再透過原生 App 身分執行單次擷取。**開始後請持續說話**，避免被 VAD 判成安靜：

```bash
"$APP/Contents/MacOS/FamilyRecorder" \
  --service listener-once \
  --program "$RUNTIME/venv/bin/family-recorder" \
  --config "$CONFIG"
```

### 步驟 5：檢查結果

```bash
cat "$HOME/xvf3800-listener-data/transcripts/$(date +%F).md"

sqlite3 "$HOME/xvf3800-listener-data/listener.sqlite3" \
  'select started_at, status, round(rms_dbfs,1), round(speech_ratio,2), text
   from segments order by id desc limit 5;'

sqlite3 "$HOME/xvf3800-listener-data/listener.sqlite3" \
  'select started_at, software_speech_ratio, hardware_speech_ratio, gate_reason
   from captures order by id desc limit 5;'
```

### 如果被略過了

若顯示 `Chunk skipped by combined silence/VAD gate`，代表 software VAD 與硬體 Speech Energy 的融合結果都未達門檻。**這是正常的隱私／儲存行為**，不是錯誤。即使沒有 WAV，低容量的 `captures`／`acoustic_samples` 遙測仍會留下，可以用來檢查為什麼被略過。

測試時可暫時放寬，驗收後再改回範例值：

```yaml
vad:
  min_speech_ratio: 0.02   # 暫時；預設 0.08
  min_rms_dbfs: -55.0      # 暫時；預設 -48.0
```

---

## 安裝常駐工作

> ⚠️ **務必先通過上面的單次錄音驗收**，且已執行 `install_menubar.sh`，再安裝常駐工作。

```bash
./scripts/install_launchd.sh          # listener 常駐
./scripts/install_daily_summary.sh    # 每日摘要排程
```

檢查狀態與 log：

```bash
launchctl print "gui/$UID/com.familyrecorder.listener"
launchctl print "gui/$UID/com.familyrecorder.summary"
tail -f "$HOME/xvf3800-listener-data/logs/listener.log"
tail -f "$HOME/xvf3800-listener-data/logs/listener.error.log"
```

listener 遇到拔線或裝置暫時不可用時，會依 `audio.retry_seconds` 重試；重新插入後會再次自動選擇裝置。

---

## 下一步

1. **[校準房間方向](hardware.md#方向校準)** —— 讓 `0°` 代表你定義的正前方。
2. **[註冊家庭成員聲音樣本](speakers.md)** —— 讓逐字稿能標出「可能是誰」。
3. **[比較麥克風擺位](hardware.md#mic-placement-test)** —— A/B/C 三個位置實測 CER。
4. **[調整設定](configuration.md)** —— 靈敏度、保留策略、摘要時間。
5. **[設定 Google Calendar](daily-summary.md#google-calendar-候選事件)** —— 讓摘要中的事件可以一鍵加入日曆。
6. **[換一個應用場景](use-cases.md)** —— 課後複習、夢境記錄、靈感備忘。
7. **[跑完 31 項實機驗收清單](development.md#驗收清單)** —— 確認每一條路徑都正常。

遇到問題請看 **[常見問題](troubleshooting.md)**。
