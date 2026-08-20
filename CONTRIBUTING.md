# 貢獻指南

[English](CONTRIBUTING.en.md) · **繁體中文**

歡迎參與 FamilyRecorder。這份文件說明怎麼提出改動、有哪些慣例，以及哪些方向最需要協助。

---

## 最需要協助的方向

| 方向 | 為什麼有用 |
|---|---|
| **其他麥克風陣列的支援** | 目前綁定 XVF3800。routing 與 telemetry 的實測 response 很難憑空推測 |
| **新場景的 prompt 範本** | 直接進 [應用場景指南](docs/use-cases.md)，其他人立刻可用 |
| **非中文語系的使用回報** | 目前這部分幾乎沒有實際資料 |
| **文件翻譯與修正** | 特別是英文版的用詞 |
| **[31 項驗收清單](docs/development.md#驗收清單)上的失敗** | 任何一項在你機器上失敗都是明確的 bug |

---

## 開 issue 之前

**先移除敏感內容。** log、SQL 查詢結果與 `doctor` 輸出可能包含：

- 逐字稿內容
- 家庭成員姓名
- 檔案路徑中的使用者名稱
- 日曆 ID 與顯示名稱

貼上前請先代換掉。

附上這些會很有幫助：

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"

"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" doctor
sw_vers
```

> 🔒 **安全性問題請不要開公開 issue。** 見 [安全政策](SECURITY.md)。

---

## 開發環境

```bash
git clone https://github.com/pcpcchen-coder/FamilyRecorder.git
cd FamilyRecorder
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

送出 PR 前，這四項都必須通過：

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest --cov=family_recorder
.venv/bin/python -m build
```

CI 執行的就是這四項。詳見 [開發與測試](docs/development.md)。

---

## 程式碼慣例

### 相依方向

模組相依**刻意保持單向**：底層模組不 import 上層模組。

```text
config → devices/audio/metrics → transcriber/direction/speakers/hallucination/storage → listener/summary → cli
```

新增模組時請放進這個層級關係，不要製造循環相依。完整相依圖見 [系統架構 → 模組地圖](docs/architecture.md#模組地圖)。

### 樣式

- `ruff`：line-length 100、target `py311`、規則集 `E` `F` `I` `UP` `B` `SIM`
- 型別標註：新程式碼請標註公開函式的參數與回傳值
- 資料類別：不可變資料優先使用 `@dataclass(frozen=True)`

### 測試

**CI 不依賴實體硬體。** 新功能請提供可在無 XVF3800 的環境執行的隔離測試。既有測試示範了怎麼模擬裝置回應：

```bash
.venv/bin/pytest tests/test_direction.py -v   # USB response 解碼
.venv/bin/pytest tests/test_listener.py -v    # 閘門決策
.venv/bin/pytest tests/test_summary.py -v     # 純文字邊界
```

> 硬體相關的改動，仍請在實機跑過 [驗收清單](docs/development.md#驗收清單)相關項目，並在 PR 說明中註明跑了哪幾項。

---

## 設計原則

改動如果牴觸以下任一項，請在 PR 中明確說明理由：

| 原則 | 意義 |
|---|---|
| **邊界可測試** | 不要用「prompt 會要求它不要這樣做」來取代結構上的限制 |
| **安靜不產生資料** | 不要為了方便而在靜音時也寫檔 |
| **單一感測器不能獨斷** | software 與 hardware 證據要互相制衡 |
| **近似要說成近似** | 不要把 `speaker_confidence` 呈現成身分機率 |
| **失敗要降級不要中止** | 遙測失敗時錄音必須繼續 |
| **可以完整移除** | 新增的檔案要納入解除安裝範圍，或明確說明為什麼不納入 |

以及 [明確非目標](docs/privacy.md#明確非目標) —— 那些項目不接受 PR。

---

## 文件慣例

**每一篇文件都有中英文兩版：** `檔名.md` 是繁體中文，`檔名.en.md` 是英文。

改動文件時：

1. **兩個版本都要改。** 只改一邊會讓兩份文件漂移。
2. 頂部保留語言切換連結。
3. 使用一致的標記：✅ 已實作、🟡 需手動設定、🚧 規劃中、❌ 刻意不做、⚠️ 注意事項。
4. **不要把規劃中的功能寫成已實作的。**
5. 文件中的預設值要與程式碼一致。

### Mermaid 圖

架構圖使用 Mermaid，GitHub 可原生渲染。加入新圖時：

- 節點標籤用引號包起來：`A["文字"]`
- 配色用 `classDef` 指定 `fill`、`stroke` 與 `color` 三者，深淺色模式才都可讀
- 送出前確認語法可解析

---

## Pull request

1. 從 `main` 開一個分支。
2. 一個 PR 做一件事。
3. commit 訊息用祈使句描述改了什麼與為什麼。
4. 送出前跑完上面四項檢查。
5. PR 說明中寫清楚：改了什麼、為什麼、怎麼驗證的。硬體相關請註明跑過哪些驗收項目。

---

## 授權

送出貢獻即表示同意以 [MIT License](LICENSE) 授權你的貢獻。
