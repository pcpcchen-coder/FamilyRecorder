# 智慧家庭狀態整合：官方可行性與本機基礎

本階段的結論很明確：FamilyRecorder 可以安全地建立跨平台、唯讀的智慧家庭事件日誌，
但目前不能在原生 macOS App 內直接登入 Google Home。已完成的範圍是 provider-neutral
資料模型、SQLite、fake provider、companion bridge 契約、隱私 allowlist、摘要時間線、
選單狀態與離線測試；沒有建立任何外部開發者專案、登入、訂閱或控制家電。

研究日期：2026-08-16。以下判斷只引用各平台官方文件。

## 平台能力矩陣

| Provider | 官方 macOS 路徑 | 狀態取得 | 本階段決策 |
|---|---|---|---|
| Google Home APIs | 官方 Home APIs SDK 只列 Android、iOS；iOS SDK 不能直接連進現有原生 AppKit 程式 | iOS Device/Structure APIs、Combine subscription、History API | 保留 `google_home` provider 與 signed iOS/Android companion bridge；不偽裝成已可登入 |
| Apple Home/HomeKit | HomeKit framework 官方 availability 不含原生 macOS，包含 iOS/iPadOS/Mac Catalyst 等 | `HMAccessoryDelegate` characteristic notification | 保留 signed iOS/Mac Catalyst companion boundary；未加 entitlement、未要求權限 |
| Tuya Cloud | macOS 可呼叫官方 HTTPS OpenAPI；即時狀態使用官方 Message Service/Pulsar | polling、status report、Pulsar message | 保留 cloud adapter boundary；等待使用者建立正確區域的 cloud project、連結帳號與選擇方案 |
| Matter | 可建立 controller 並訂閱 attribute/event，但需 commissioning、fabric 與憑證 | Matter subscription | 只保留 provider 擴充點；不把它當成既有 Google/Apple Home 的通用讀取器 |
| Home Assistant | 官方 WebSocket API 可訂閱 `state_changed`，另有 OAuth／long-lived token | WebSocket subscription、REST | contract 已能容納小型 adapter；本階段維持 Google-first，不連線 |
| Fake | 不需帳號或網路 | fixture polling/subscription | 已實作，供 CI 與本機驗收 |

## 官方研究決策

### Google Home APIs

Google 的 [Home APIs 首頁](https://developers.home.google.com/apis) 只列 Android 與 iOS SDK。
[iOS SDK 設定](https://developers.home.google.com/apis/ios/sdk) 雖然需要 Mac、Xcode，執行目標仍是
iOS 17+；同時要求 App Attest、App Group 與正確 provisioning，且不支援 simulator。
[iOS release notes](https://developers.home.google.com/apis/ios/release-notes) 在研究日所列最新版為
1.9.1（2026-06-26）；版本更新不改變官方平台清單仍只有 Android/iOS 的結論。
[OAuth 設定](https://developers.home.google.com/apis/ios/oauth) 要求 Google Cloud project、啟用
Home API、建立 iOS OAuth client；未註冊前的測試人數上限為 100，而文件目前仍把 iOS app
registration 標成尚未開放。

正式 companion 可透過 [Device/Structure API](https://developers.home.google.com/apis/ios/device)
讀取結構與裝置，透過 [Combine subscription](https://developers.home.google.com/apis/ios/device/monitor)
觀察狀態；History API 的
[HistoryItem](https://developers.home.google.com/reference/swift/GoogleHomeSDK/Structs/HistoryItem)
與 [HistoryQuery](https://developers.home.google.com/reference/swift/GoogleHomeSDK/Classes/HistoryQuery)
可提供帶時間的歷史資料。官方
[iOS supported device types](https://developers.home.google.com/apis/ios/supported-device-types)
清單包含 Coffee Maker 與 Extractor Hood。配額文件列出
[每 project 每分鐘 30,000 次呼叫](https://developers.home.google.com/apis/ios/quota-management)，
超限應使用 exponential backoff。

因此現有 native macOS AppKit 程式不可直接使用官方 Google Home SDK。正確邊界是：Google
登入與 Home APIs 呼叫只存在於簽章、通過 App Attest 的 companion；companion 只傳送
使用者選定的結構、裝置、屬性與無憑證狀態事件給 Mac。禁止逆向 endpoint、cookie 匯入、
私有 API 或要求 Google 密碼。

### Apple Home/HomeKit

Apple [HomeKit framework](https://developer.apple.com/documentation/homekit) 的官方 availability
列出 iOS、iPadOS、Mac Catalyst、tvOS、visionOS、watchOS，沒有 native macOS。
[Enabling HomeKit in your app](https://developer.apple.com/documentation/homekit/enabling-homekit-in-your-app)
要求 HomeKit capability／entitlement、`NSHomeKitUsageDescription`、簽章 provisioning，並由
使用者在系統提示中授權。狀態變更可由
[HMAccessoryDelegate](https://developer.apple.com/documentation/homekit/hmaccessorydelegate)
接收 characteristic 更新。

因此本專案不會只在既有 AppKit target 加一個 entitlement 就宣稱可讀 Apple Home。未來可採
iOS 或 Mac Catalyst companion，而且須由開發者團隊簽章並由使用者授權。

### Tuya Cloud Development

Tuya 使用區域化 data center；應先依官方
[Data Center Introduction](https://developer.tuya.com/en/docs/iot/Data_Center_Introduction?id=Kav2hlac2ppnw)
與 [OEM App distribution](https://developer.tuya.com/en/docs/iot/oem-app-data-center-distributed?id=Kafi0ku9l07qb)
選擇帳號實際區域。台灣的新 Smart Life app 資料目前對應 Singapore data center，不能把
endpoint 寫死後跨區猜測。帳號連結可採官方
[OAuth authorization code](https://developer.tuya.com/en/docs/iot/authorization-code-page-usage?id=Kdkyz44dz6a7r)，
OpenAPI 要依官方 [HMAC-SHA256 signature](https://developer.tuya.com/en/docs/iot/new-app-singnature?id=Kdnqza5d7iwkc)
簽章。狀態可由
[Device Status Report](https://developer.tuya.com/en/docs/cloud/f06dc21023?id=Kcp2l1a9zj0i3)
取得，即時事件使用
[Message Service](https://developer.tuya.com/en/docs/iot/manage-messages?id=Ka49p7loog3ze)／
[Pulsar subscription](https://developer.tuya.com/en/docs/iot/subscribe?id=Kbwtw7fhhjabw)。實作前也必須依
[frequency control](https://developer.tuya.com/en/docs/iot/frequency-control?id=Kcojz2r2dg1f6)
與 [membership pricing](https://developer.tuya.com/en/docs/iot/membership-service?id=K9m8k45jwvg9j)
選方案；官方 trial 有 calls、messages、data center 與裝置數限制。

Tuya adapter 在技術上可由 macOS 執行，但 client secret、token 只能放 Keychain，且外部 cloud
project、授權服務、資料中心、帳號連結與可能付費都必須由使用者決定後才進行。

### Matter 與 Home Assistant

Matter 官方 SDK 的
[controller subscription 指南](https://github.com/project-chip/connectedhomeip/blob/master/docs/development_controllers/chip-tool/chip_tool_guide.md)
可訂閱 attribute/event，但 controller 是自己的 fabric，需要 commissioning；CSA 的
[Multi-Admin 說明](https://csa-iot.org/newsroom/peeking-under-the-hood-of-your-matter-smart-home/)
也顯示裝置分享依 fabric 管理。它不是不經授權就能讀取既有 Google／Apple home 的捷徑。

Home Assistant 有官方
[WebSocket API](https://developers.home-assistant.io/docs/api/websocket/) 與 `state_changed`
subscription，也有官方 [authentication API](https://developers.home-assistant.io/docs/auth_api/)。
provider contract 已能容納這條路徑；等 Google foundation 驗收後，可再做一個小型、唯讀 adapter。

## Provider-neutral 設計

`family_recorder.home` 將 provider adapter 與核心資料分開：

- `HomeProvider`：共同 `sync(cursor)` 與 `subscribe(cursor)` 唯讀介面。
- `HomeAccount`：只含非秘密 metadata 與 Keychain item reference。
- `HomeStructure`、`HomeRoom`、`HomeDevice`、`HomeCapability`：探索與選擇階層。
- `HomeStateSnapshot`、`HomeStateEvent`：原始值、正規化值、provider／observer 時間與來源。
- `SyncCursor`、`ConnectionHealth`：增量同步、斷線、重授權與 retry 狀態。

未知 capability 的 provider key、raw value、raw payload 會完整留在 SQLite。正規化失敗不會
丟值，也不會自動讓該屬性進摘要。共同 service 支援 polling/subscription、指數退避、
event dedupe、debounce、provider clock skew fallback、狀態起訖合併與高頻數值 coalescing。

SQLite migration 在既有 `listener.sqlite3` 內新增：

- `home_provider_accounts`：provider、transport、Keychain reference、連線健康；不存 secret。
- `home_structures`、`home_rooms`、`home_devices`、`home_capabilities`：探索結果與原始 metadata。
- `home_state_snapshots`、`home_state_events`：去重鍵、來源、原始／正規化狀態、起訖、時區、
  provider/observer time quality 與 clock skew。
- `home_sync_cursors`、`home_connection_errors`：同步位置、retry/reauthorization 診斷。

## Companion bridge v1

[`home-companion-v1.schema.json`](schemas/home-companion-v1.schema.json) 定義 Mac 接受的最小 JSON
邊界。`schema_version` 必須是 `1`；provider 只能是 `google_home` 或 `apple_home`，transport
必須是 `companion_bridge`。payload 出現 token、API/private key、authorization、password、
credential 或 secret（包括巢狀欄位）會被拒絕；companion 也不能替 Mac 指定 Keychain item。

bridge 是資料契約，不是尚未存在的登入實作。正式傳輸還必須補上 companion 簽章驗證、
本機配對、重放保護與 Keychain identity；完成前只可用 fixture/mock 驗證，不應開放網路 listener。

## 最短、非技術授權流程（尚未執行）

### Google Home

1. 使用者／專案擁有者建立 Google Cloud project、啟用 Home API、設定 OAuth consent 與 iOS client。
2. Apple Developer team 建立 App ID、App Group、App Attest 與 provisioning；建置 signed companion。
3. 使用者在 companion 按「使用 Google 登入」，同意 Home 權限，選擇要分享的 home／room／device。
4. Mac 端完成本機配對，再逐一勾選「本機記錄」與更嚴格的「允許文字進摘要」。

步驟 1–3 涉及外部帳號、開發者設定與同意；目前停在這裡等待使用者決定。

### Apple Home

1. 專案擁有者決定 iOS 或 Mac Catalyst companion，使用 Apple Developer team 簽章並加入 HomeKit capability。
2. 使用者第一次開啟時閱讀用途說明，在系統提示中允許 Home 存取。
3. 使用者選 home／room／device／capability，Mac 端再設定記錄與摘要 allowlist。

### Tuya

1. 使用者建立 Tuya Cloud project，依 Smart Life 帳號區域選 data center，選擇 trial 或付費方案。
2. 啟用所需的唯讀／狀態通知服務，以 QR/OAuth 連結自己的 app account。
3. FamilyRecorder 只把 client secret/token 寫入 macOS Keychain，YAML 只留 item reference 與非秘密 endpoint。
4. 使用者在選單選 home／room／device／capability；預設不允許任何項目進摘要。

## 本機驗收

以下不需要真實帳號或網路：

```bash
.venv/bin/family-recorder --config config.example.yaml \
  home-sync-fixture --fixture tests/fixtures/home/fake_home.json
.venv/bin/family-recorder --config config.example.yaml home-status
.venv/bin/pytest -q tests/test_home.py tests/test_summary.py tests/test_config.py
```

fixture 與測試驗證 migration、未知資料保留、正規化、去重、時間合併、高頻 coalescing、
clock skew、allowlist、文字摘要、重試與 companion credential rejection。所有 provider contract
都是唯讀；本階段沒有 `execute`、`setState`、remote command 或家電控制介面。
