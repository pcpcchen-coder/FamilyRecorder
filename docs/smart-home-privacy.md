# 智慧家庭資料與隱私邊界

FamilyRecorder 對智慧家庭資料採兩層明確同意，預設兩層都關閉：

1. `record_allowlist` 決定哪些裝置屬性可以進本機 SQLite。
2. `summary_allowlist` 必須是第一層的子集，決定哪些屬性可先在本機轉成簡短文字事件，
   再和當日逐字稿一起送進純文字摘要。

關閉第二層後，既有本機原始事件不會進後續摘要；不是只在首次收件時做一次過濾。
未知 capability 即使獲准本機保存，也只保留 provider key/value，不會自動送出或讓模型猜意思。
高頻溫度、風速等數值預設合併成低頻 snapshot，也不會自動形成摘要事件。

## 可留在本機的資料

- 使用者勾選的原始裝置狀態、provider key、原始 payload、正規化狀態。
- provider 與本機觀測時間、時區、clock skew、事件起訖、dedupe key、sync cursor。
- home／room／device 顯示名稱與非秘密 metadata。
- 連線健康、錯誤、retry 與重新授權狀態。
- Keychain item reference；reference 不是 token 或 secret。

## 可進每日摘要的資料

只有 `summary_allowlist` 中的屬性，經本機規則轉成例如：

```text
07:31–07:36｜廚房／咖啡機運作
19:08–19:26｜廚房／抽油煙機運作
```

摘要收到的是這段文字，不是 SQLite、完整 home graph、raw JSON、credential 或音訊。家電時間線
是與語音逐字稿並列的獨立證據；固定摘要契約禁止它覆蓋逐字稿、推定誰在場、把狀態歸因給
某位家庭成員，或偽造對話內容。

## 永遠不得進 YAML、bridge 或摘要的資料

- OAuth access/refresh token、authorization header、client secret、Tuya secret、密碼。
- Google／Apple／Tuya 帳密、browser cookie、私人 endpoint。
- 原始 WAV、speaker profile、完整智慧家庭資料庫。
- 未勾選的裝置／屬性或未知屬性的推測解讀。

正式 adapter 的 credential 只能透過 macOS
[Keychain](https://developer.apple.com/documentation/security/storing-keys-in-the-keychain) 保存。
`config.yaml` 只能含 `keychain_item_ref`。移除 provider 時應刪除該 adapter 對應的 Keychain item、
移除 active config/allowlist 並停止訂閱；本機歷史事件預設保留，除非使用者另外選擇刪除資料。
目前沒有真實 adapter 或 credential，因此「移除」只會取消本機連線設定並保留歷史。

## 控制與推論限制

- provider protocol 沒有控制命令；不提供遠端開關、automation 或 action tool。
- 智慧家庭狀態不能改寫音訊辨識結果；未來聲音分類只能以時間戳交叉驗證，兩邊仍保留來源。
- clock skew 超過設定值時，以本機 observed time 記錄並標示 time quality，不把不可信 provider
  時間當成精確事實。
- provider error 不得阻斷錄音、Whisper、speaker、direction、calendar 或每日摘要既有路徑。
