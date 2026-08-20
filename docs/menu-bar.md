# 選單列與服務管理

[English](menu-bar.en.md) · **繁體中文** · [返回文件索引](README.md)

安裝後，右上角會出現一個波形圓形圖示。日常使用幾乎不需要開終端機 —— 包含解除安裝。

---

## 目錄

- [圖示狀態](#圖示狀態)
- [選單功能](#選單功能)
- [暫停如何運作](#暫停如何運作)
- [三個 LaunchAgent](#三個-launchagent)
- [一鍵解除安裝](#一鍵解除安裝)

---

## 圖示狀態

| 圖示 | 意義 |
|---|---|
| 波形圓形 | 錄音中 |
| 暫停符號 | 已暫停 |
| 警告符號 | listener 異常或未執行 |

---

## 選單功能

### 狀態與資料

- 顯示「**錄音中／已暫停／服務未執行**」，以及目前的 Whisper 與摘要模型。
- 快速開啟**今天的逐字稿**與**摘要**。
- 開啟**全部資料、音訊、log、設定檔**所在資料夾。

### 暫停

- 暫停 **15 分鐘**、**1 小時**，或**直到手動恢復**。

### 本機 Whisper

- 從**實際已下載**的 `ggml-*.bin` 清單切換模型。切換後會重啟 listener。
- 「**下載其他模型…**」依三組分類直接下載新的多語模型：
  - 標準
  - 量化省空間
  - 舊版相容

  會顯示預估容量、支援失敗後續傳，完成 **GGML 格式驗證**後才切換並重啟 listener。**原有模型不會刪除。**

清單對應專案固定使用的 whisper.cpp v1.8.1 官方模型清單。FamilyRecorder 預設為中文，因此**不顯示 `.en` 英文限定版**；可選 Tiny、Base、Small、Medium、Large v1/v2/v3、Large v3 Turbo 及其多語 Q5／Q8 量化版本。模型從 whisper.cpp 官方下載腳本指定的 Hugging Face repository 取得，名稱經 **allowlist 驗證**，未完成的檔案以 `.partial` 保存供下次續傳。

也可用指令：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" \
  download-whisper-model --model small-q5_1
```

### 更換模型 → ChatGPT 摘要

- 使用 ChatGPT 帳號預設模型，或輸入帳號實際可用的自訂 Codex 模型名稱。
- 以**多行編輯器**自訂每日摘要 Prompt，或一鍵恢復內建格式。

變更只套用到之後產生或重新執行的摘要。摘要模型在每次執行時重新讀取，**不需要重啟服務**。

### 常用字詞校正

逐行維護姓名與術語，例如 `陳樂融`。儲存後會**重啟 listener** 套用。

字詞會加入本機 Whisper 提示，並在辨識後保守校正無歧義的單一字差近似結果。**只在本機使用，不會送到雲端。**

### 防幻覺過濾

- 查看**今天的聲學／文字攔截數**。
- 選擇**寬鬆、平衡或嚴格**保護。
- 「**進階調整門檻…**」可直接編輯百分比、SNR、log probability、重複視窗等每一項設定。

修改後會重啟 listener。三段預設的實際數值見 [設定參考](configuration.md#三段預設)。

### 家庭成員與人聲

- 編輯成員清單。
- 查看註冊狀態（例如 `3/3`）。
- **錄製／更新**或**刪除**個別聲音樣本。

錄製時會先**主動檢查麥克風授權**；未允許時不會開始一段必定失敗的錄音，並可直接打開對應的系統設定頁。錄製期間 listener 會暫停，完成後自動恢復。

詳見 [家庭成員與方向](speakers.md)。

### 聲音方向

- 開關方向判斷。
- 「**測試目前方向…**」在不寫入逐字稿的情況下顯示方位、角度、穩定度與有效樣本數。
- 「**把目前位置校準為正前方…**」讓使用者站在指定位置說話，一鍵校準房間的 `0°`。

詳見 [硬體與收音 → 方向校準](hardware.md#方向校準)。

### Google Calendar

- 選擇全家預設日曆。
- 為每位成員綁定多個日曆並指定預設。
- 逐筆確認 AI 候選事件，或一次同意後自動加入。

詳見 [每日摘要與行事曆](daily-summary.md#google-calendar-候選事件)。

### 操作

- **立即整理今天** —— 明確傳入今天日期，不是排程的「昨天」。
- **重新啟動錄音服務**
- **執行完整 `doctor` 檢查**
- **解除安裝 FamilyRecorder…** —— 打開獨立的解除安裝器。

### 結束選單列程式

「結束選單列程式」**只會關閉圖示，不會停止 listener**。這是刻意的正常退出，LaunchAgent 不會立即重開；重新登入或重跑 `install_menubar.sh` 即可再次顯示。

---

## 暫停如何運作

暫停狀態存在 `data_dir/control.json`，**不是只存在 UI 記憶體**。

| 行為 | 說明 |
|---|---|
| 反應時間 | listener 每秒檢查一次，約 **1 秒內**關閉麥克風串流 |
| 進行中的 chunk | **直接丟棄，不保存** |
| 選單列程式重啟 | 不會意外恢復錄音 |
| 定時暫停到期 | 由 listener **自動恢復** |
| 選單列程式關閉 | 暫停狀態仍然有效 |

指令等價：

```bash
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" pause --minutes 60
"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" resume
```

---

## 三個 LaunchAgent

全部是**使用者層級 LaunchAgent**，不是 root daemon。

| 識別碼 | 觸發方式 | 職責 |
|---|---|---|
| `com.familyrecorder.listener` | `RunAtLoad` ＋ 失敗後 `KeepAlive` | 常駐錄音與轉錄 |
| `com.familyrecorder.summary` | `StartCalendarInterval`，時間讀自 YAML | 每日摘要 |
| `com.familyrecorder.menubar` | 登入後啟動，僅在非預期結束後重啟 | 原生 AppKit 選單列 |

```bash
launchctl print "gui/$UID/com.familyrecorder.listener"
launchctl print "gui/$UID/com.familyrecorder.summary"
launchctl print "gui/$UID/com.familyrecorder.menubar"

tail -f "$HOME/xvf3800-listener-data/logs/listener.log"
tail -f "$HOME/xvf3800-listener-data/logs/listener.error.log"
tail -f "$HOME/xvf3800-listener-data/logs/summary.error.log"
tail -f "$HOME/xvf3800-listener-data/logs/menubar.error.log"
```

手動重啟 listener：

```bash
launchctl kickstart -k "gui/$UID/com.familyrecorder.listener"
```

> ⚠️ 改了 `summary.hour` / `summary.minute` 之後，要**重跑 `./scripts/install_daily_summary.sh`**，plist 才會更新。

launchd 環境變數中**沒有任何 API key 或 Codex token**；summary 工作只提供 `HOME`，讓官方 CLI 自己找到它保存的登入。

三個工作都關聯到 `/Applications` 裡的**同一個 App**，避免隱藏或使用者層級路徑造成 Spotlight／TCC 身分快取不一致。

---

## 一鍵解除安裝

### 建議做法

1. 點選單列波形圖示 →「**解除安裝 FamilyRecorder…**」。
2. 選擇模式：
   - 「**只移除程式，保留家庭資料與設定**」
   - 「**完整移除，包括所有模型、錄音與紀錄**」
3. 確認畫面列出的程式／模型、家庭資料與設定**容量**，再按解除安裝。
4. 所有選定內容會先移到**同一個垃圾桶子資料夾**；確認不需復原後再清空垃圾桶。

選單被關閉後清理仍會繼續 —— 解除安裝器是**獨立簽署的程式**，所以它能先停掉三個 LaunchAgent，再移動正在執行的選單列 App。

### 兩種模式的差別

| 內容 | 只移除程式 | 完整移除 |
|---|:---:|:---:|
| 三個 LaunchAgent | ✅ 停止並移除 | ✅ |
| Python runtime、選單列 App、解除安裝器 | ✅ | ✅ |
| whisper.cpp 與所有本機模型 | ✅ | ✅ |
| 原始 WAV、逐字稿、摘要、SQLite | ❌ **保留** | ✅ |
| 人聲特徵、擺位測試、暫停狀態、logs | ❌ **保留** | ✅ |
| `config.yaml` 及其安裝備份 | ❌ **保留** | ✅ |
| 麥克風與行事曆權限紀錄 | ❌ 保留 | ✅ |

「只移除程式」保留 `data_dir` 和 `config.yaml`，方便日後重新安裝。

### 明確在邊界之外

**兩種模式都不會**：

- 登出或移除 **ChatGPT／Codex**
- 刪除 **Homebrew、Python、Git、CMake、PortAudio** 等可能由其他程式共用的工具
- 刪除 **GitHub repo、本機原始碼 checkout** 或另外下載的 DMG

### 安全機制

| 機制 | 作用 |
|---|---|
| `.familyrecorder-data` 標記 | 讓解除安裝器確認這是 FamilyRecorder 專用資料夾 |
| 沒有標記的路徑 | 只搬走**已知的**子目錄與資料庫，不會把整個 Documents 或其他共用資料夾移走 |
| 拒絕清單 | 拒絕以 `/`、使用者家目錄、垃圾桶、LaunchAgents 目錄作為移除目標 |
| 移到垃圾桶 | **清空垃圾桶前都還能復原** |

### 從原始碼

若圖形介面無法使用：

```bash
./scripts/uninstall_family_recorder.sh inspect
./scripts/uninstall_family_recorder.sh uninstall keep-data  # 保留家庭資料與設定
./scripts/uninstall_family_recorder.sh uninstall all        # 完整移除
```

舊的 `./scripts/uninstall_launchd.sh` **只適合暫時停止並移除三個 LaunchAgent**，不會刪除其他內容。

若選單列已損壞，也可從最新版 DMG 直接打開「解除安裝 FamilyRecorder.app」。

---

## 相關文件

- [CLI 指令參考](cli.md) —— 每一個選單動作的指令等價
- [系統架構 → 選單列控制路徑](architecture.md#選單列控制路徑) —— 序列圖
- [系統架構 → 解除安裝邊界](architecture.md#解除安裝邊界)
- [常見問題 → 選單列沒有圖示](troubleshooting.md#選單列沒有圖示)
