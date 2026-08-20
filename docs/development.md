# 開發與測試

[English](development.en.md) · **繁體中文** · [返回文件索引](README.md)

---

## 目錄

- [本機開發環境](#本機開發環境)
- [測試策略](#測試策略)
- [程式碼結構](#程式碼結構)
- [建置 DMG](#建置-dmg)
- [驗收清單](#驗收清單)

---

## 本機開發環境

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest --cov=family_recorder
```

專案需要 Python 3.11 以上。`ruff` 設定為 line-length 100、target `py311`，啟用 `E`、`F`、`I`、`UP`、`B`、`SIM` 規則集。

### 依賴

| 套件 | 用途 |
|---|---|
| `numpy` | 音訊分析、特徵抽取 |
| `PyYAML` | 設定檔 |
| `pyusb` | XVF3800 USB vendor control |
| `sounddevice` | PortAudio 綁定 |
| `webrtcvad-wheels` | WebRTC VAD |

開發額外需要 `build`、`pytest`、`pytest-cov`、`ruff`。

---

## 測試策略

**CI 不直接依賴實體硬體。** 以下都有隔離測試：

- 裝置選擇與評分
- routing response 解碼、beamformed／raw 判定
- 四束 float32 Speech Energy 解析
- software／hardware VAD 融合
- 共同 time series 對齊
- 雙聲道 downmix 與取樣率轉換
- Whisper CLI 呼叫與 JSON 解析
- SQLite migration 與 Markdown 附加
- 人聲近似分類
- Retention
- 純文字摘要路徑
- CER 報告
- 防幻覺聲學層與文字層
- 暫停狀態的原子讀寫
- 解除安裝的安全檢查
- macOS 識別一致性

```bash
.venv/bin/pytest tests/test_listener.py -v      # 閘門決策
.venv/bin/pytest tests/test_summary.py -v       # 純文字邊界與契約
.venv/bin/pytest tests/test_hallucination.py -v # 防幻覺
.venv/bin/pytest tests/test_uninstaller.py -v   # 解除安裝安全檢查
```

> ⚠️ **發佈前仍應在 XVF3800 實機執行** `diagnose-beamforming`、`doctor` 與語音／靜音採樣。CI 通過不等於實機正常 —— 完整清單見下方[驗收清單](#驗收清單)。

### CI

`.github/workflows/ci.yml` 在每次 PR 與推向 `main` 時執行：

1. `ruff check .`
2. `ruff format --check .`
3. `pytest --cov=family_recorder`
4. `python -m build`（wheel 與 sdist）

---

## 程式碼結構

```text
src/family_recorder/
├── config.py           # YAML schema 與預設值；所有模組的相依起點
├── devices.py          # macOS 輸入裝置列舉與評分
├── audio.py            # AudioRecorder、downmix、重新取樣、WAV I/O
├── metrics.py          # RMS、SNR、VAD ratio、低頻比、窄頻集中度
├── transcriber.py      # whisper-cli 子程序與 JSON 解析
├── direction.py        # XVF3800 USB control、DoA、Speech Energy、環狀分群
├── speakers.py         # 特徵抽取、profile 儲存、近似人別
├── hallucination.py    # 聲學層與文字層攔截判斷
├── control.py          # control.json 暫停狀態
├── storage.py          # SQLite schema／migration、Markdown、retention
├── listener.py         # 常駐主迴圈
├── summary.py          # 每日摘要、輸出契約、行事曆擷取
├── placement.py        # 擺位測試與 CER
├── model_manager.py    # 模型清單、下載、驗證
├── config_editor.py    # 保留註解的目標式 YAML 編輯
└── cli.py              # 全部子指令；唯一進入點
```

相依關係**刻意保持單向**：底層模組不認識上層。完整相依圖見 [系統架構 → 模組地圖](architecture.md#模組地圖)。

### 其他目錄

| 目錄 | 內容 |
|---|---|
| `menubar/` | Swift 選單列 App 原始碼、`Info.plist`、entitlements |
| `packaging/` | Swift 安裝器與解除安裝器、payload 腳本 |
| `launchd/` | 三個 LaunchAgent 的 plist 樣板 |
| `scripts/` | 安裝、解除安裝、DMG 建置腳本 |
| `tests/` | 17 個測試檔 |

---

## 建置 DMG

在 Apple Silicon Mac 上：

```bash
./scripts/build_dmg.sh
```

產物為 `dist/FamilyRecorder-<版本>-arm64.dmg` 與對應的 `.sha256`。

> 若要公開散布且不顯示 Gatekeeper 未公證警告，發行者還需使用 **Developer ID Application 憑證**簽署並送 Apple **notarization**。一般 Apple Development 憑證**不等同**公開發行公證。

---

## 驗收清單

實機發佈前的 31 項檢查。這份清單同時是本專案「哪些行為算正確」的規格。

### 基礎收音

1. `list-devices` 看得到 XVF3800/XMOS，`doctor` 選到正確裝置。
2. `listen --once` 後 WAV 是 16 kHz、mono、PCM16。
3. 安靜 30 秒不產生 WAV／逐字稿；持續說話會產生。
4. 當日 Markdown 有正確時間標題與繁中內容。
5. SQLite 最新列的 `status='transcribed'`，且 RMS／speech ratio 合理。
6. 拔掉 XVF3800，listener log 顯示 retry；插回後恢復。
7. 把 `keep_audio_days` 暫設為 0，執行 `cleanup` 可移除舊 WAV，不動逐字稿。

### 摘要與隱私邊界

8. 手動 `summary --date ...` 只產生 Markdown summary，雲端程式路徑未讀 WAV 或聲音特徵。
9. `codex login status` 與 `doctor` 都顯示 ChatGPT 已登入；YAML、plist、環境變數與 Python dependencies 均沒有 OpenAI API key。

### 服務與選單列

10. 重開機／重新登入後三個 `launchctl print` 工作存在，右上角有 FamilyRecorder 圖示。
11. 選單列暫停後不再產生 chunk，恢復後 listener 繼續；模型清單與資料夾捷徑可用。

### 擺位測試

12. A/B/C placement report 有每句轉錄、RMS、SNR、speech ratio、CER 與彙總表。

### 家庭成員人別

13. 設定三位測試成員並完成樣本後，選單顯示 3/3；逐字稿出現「可能：某人」或保守的「可能多人／不確定」，SQLite 三個 speaker 欄位同步。
14. 刪除其中一位樣本後，對應 `speaker-*.json` 消失，其他成員不受影響。

### 摘要契約

15. 摘要的「事件時間軸」、重要消息、決策與待辦均保留 `約 HH:MM`／時間區間；無法對應者標示「時間不明」。
16. 摘要對每個有來源人別的重要項目保留「可能說話者」，並有「家庭成員重點」分組；可能多人、不確定及未標記內容不會硬分配，說話者也不會自動成為待辦負責人。
17. 把測試逐字稿限制成多段輸入後，每一段仍保留其 `### 時間 — 可能：某人` 標題，最終整併請求也包含相同人別契約。

### 解除安裝與封裝

18. 在隔離暫存 HOME 驗證解除安裝兩種模式：保留模式不碰逐字稿與設定；完整模式移除全部 FamilyRecorder 內容；無標記的共用資料夾保留無關檔案。
19. DMG 同時包含安裝器與解除安裝器，兩者簽章、版本與內含腳本均通過驗證。
20. `ruff check .`、`ruff format --check .`、`pytest`、Swift typecheck、plist／shell 語法與套件建置全數通過。

### 方向遙測

21. `doctor` 的 XVF3800 direction telemetry 顯示 OK；選單「測試目前方向」能在說話時回傳角度。
22. 校準正前方後，從正前方、左側與右側各說一句，逐字稿分別接近 `0°`、`90°`、`270°`，SQLite 同步保存方向摘要與逐筆樣本。
23. 同一 30 秒內從兩個不同方向輪流說話時，Whisper 時間片段各自取得相符方向；同時或快速交疊時保守標示多方向／不確定。
24. 每日摘要包含「對話方向與人別線索」，重要項目保留來源方向；沒有音色姓名時不會只靠方向指定家人。

### 行事曆

25. Google Calendar 預設未確認前不建立事件；開啟 `auto_create` 必須先通過一次明確同意。成員路由可回退到成員／全家預設，自動與手動建立都更新 SQLite 狀態，重啟重試不會重複加入同一候選。

### Beamforming 與 Speech Energy

26. `diagnose-beamforming` 讀回左、右 `AUDIO_MGR_OP`；預設單聲道設定明確顯示 `[OK]` 且左聲道是 category `6` processed 或 category `8` user-chosen auto-selected beam，不是 raw category。
27. 實機靜音時 `AEC_SPENERGY_VALUES` 四束接近 0；說話時至少一束與 auto-selected beam 產生非零能量，`doctor` 顯示四值可讀。
28. SQLite 的 `captures` 對安靜與語音 chunk 都有列；`acoustic_samples` 可用同一 `capture_id + offset_ms` 查到 DoA 與四束能量，硬體能量救回 software VAD miss 時 `gate_reason='xvf3800_speech_energy'`。

### 防幻覺

29. 以硬體 Speech Energy 0%、software VAD 約 10–25%、SNR 低於 10 dB 的固定噪音測試，`captures.gate_reason` 為 `hallucination_filter:hardware_silence`，不產生逐字稿。
30. 對兩個相隔 30 秒的相同長句測試，第一筆可接受，第二筆寫入 `transcription_audits.decision='filtered'` 且不追加 Markdown；「好／嗯」等短句不受此規則影響。
31. 選單可顯示今日攔截數，寬鬆／平衡／嚴格與進階門檻修改後會保存 YAML 並成功重啟 listener。

---

## 相關文件

- [系統架構](architecture.md) —— 每個模組的職責與資料流
- [CLI 指令參考](cli.md) —— 測試時會用到的指令
- [資料與 SQLite](data-model.md#常用查詢) —— 驗收查詢
- [貢獻指南](../CONTRIBUTING.md) —— PR 流程與慣例
