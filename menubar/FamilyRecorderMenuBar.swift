import AppKit
import AVFoundation
import Darwin
import EventKit
import Foundation

struct WhisperModel: Decodable {
    let name: String
    let path: String
}

struct DownloadableWhisperModel: Decodable {
    let name: String
    let displayName: String
    let sizeLabel: String
    let category: String
    let description: String
    let installed: Bool

    enum CodingKeys: String, CodingKey {
        case name
        case displayName = "display_name"
        case sizeLabel = "size_label"
        case category
        case description
        case installed
    }
}

struct SpeakerMember: Decodable {
    let name: String
    let enrolled: Bool
    let createdAt: String?
    let sampleSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case name
        case enrolled
        case createdAt = "created_at"
        case sampleSeconds = "sample_seconds"
    }
}

struct PendingCalendarEvent: Decodable {
    let id: Int
    let summaryDate: String
    let title: String
    let startsAt: String
    let endsAt: String
    let allDay: Bool
    let notes: String
    let memberName: String
    let suggestedCalendarID: String

    enum CodingKeys: String, CodingKey {
        case id
        case summaryDate = "summary_date"
        case title
        case startsAt = "starts_at"
        case endsAt = "ends_at"
        case allDay = "all_day"
        case notes
        case memberName = "member_name"
        case suggestedCalendarID = "suggested_calendar_id"
    }
}

final class CalendarChoice: NSObject {
    let id: String
    let name: String

    init(id: String, name: String) {
        self.id = id
        self.name = name
    }
}

final class MemberCalendarChoice: NSObject {
    let member: String
    let calendarID: String

    init(member: String, calendarID: String) {
        self.member = member
        self.calendarID = calendarID
    }
}

struct RecorderStatus: Decodable {
    let paused: Bool
    let pauseLabel: String
    let listenerRunning: Bool
    let configPath: String
    let dataDir: String
    let transcriptDir: String
    let summaryDir: String
    let audioDir: String
    let logDir: String
    let todayTranscript: String
    let todaySummary: String
    let currentWhisperModel: String
    let currentWhisperModelPath: String
    let whisperModels: [WhisperModel]
    let downloadableWhisperModels: [DownloadableWhisperModel]
    let summaryModel: String
    let summaryPrompt: String
    let commonTerms: [String]
    let speakerEnabled: Bool
    let speakerMembers: [SpeakerMember]
    let speakerProfilesDir: String
    let directionEnabled: Bool
    let directionFrontAngleDegrees: Double
    let calendarEnabled: Bool
    let calendarProvider: String
    let calendarDefaultID: String
    let calendarDefaultName: String
    let calendarMemberIDs: [String: [String]]
    let calendarMemberDefaultIDs: [String: String]
    let calendarPendingEvents: [PendingCalendarEvent]

    enum CodingKeys: String, CodingKey {
        case paused
        case pauseLabel = "pause_label"
        case listenerRunning = "listener_running"
        case configPath = "config_path"
        case dataDir = "data_dir"
        case transcriptDir = "transcript_dir"
        case summaryDir = "summary_dir"
        case audioDir = "audio_dir"
        case logDir = "log_dir"
        case todayTranscript = "today_transcript"
        case todaySummary = "today_summary"
        case currentWhisperModel = "current_whisper_model"
        case currentWhisperModelPath = "current_whisper_model_path"
        case whisperModels = "whisper_models"
        case downloadableWhisperModels = "downloadable_whisper_models"
        case summaryModel = "summary_model"
        case summaryPrompt = "summary_prompt"
        case commonTerms = "common_terms"
        case speakerEnabled = "speaker_enabled"
        case speakerMembers = "speaker_members"
        case speakerProfilesDir = "speaker_profiles_dir"
        case directionEnabled = "direction_enabled"
        case directionFrontAngleDegrees = "direction_front_angle_degrees"
        case calendarEnabled = "calendar_enabled"
        case calendarProvider = "calendar_provider"
        case calendarDefaultID = "calendar_default_id"
        case calendarDefaultName = "calendar_default_name"
        case calendarMemberIDs = "calendar_member_ids"
        case calendarMemberDefaultIDs = "calendar_member_default_ids"
        case calendarPendingEvents = "calendar_pending_events"
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private let programPath: String
    private let configPath: String
    private let uninstallerPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let menu = NSMenu()
    private let eventStore = EKEventStore()
    private var availableGoogleCalendars: [EKCalendar] = []
    private var currentStatus: RecorderStatus?
    private var downloadingWhisperModel: DownloadableWhisperModel?
    private var enrollingSpeakerName: String?
    private var enrollmentPanel: NSPanel?
    private var enrollmentStatusLabel: NSTextField?
    private var enrollmentProgress: NSProgressIndicator?
    private var enrollmentTimer: Timer?
    private var enrollmentStartedAt: Date?
    private var refreshTimer: Timer?
    private var runningProcesses: [Process] = []

    init(programPath: String, configPath: String, uninstallerPath: String) {
        self.programPath = programPath
        self.configPath = configPath
        self.uninstallerPath = uninstallerPath
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        menu.delegate = self
        statusItem.menu = menu
        let calendarStatus = EKEventStore.authorizationStatus(for: .event)
        if #available(macOS 14.0, *) {
            if calendarStatus == .fullAccess {
                refreshGoogleCalendars()
            }
        } else if calendarStatus == .authorized {
            refreshGoogleCalendars()
        }
        refreshStatus(rebuildMenu: true)
        if AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined {
            // A first-run foreground explanation makes the following macOS TCC
            // sheet reliable and gives the user context before they decide.
            NSApp.setActivationPolicy(.regular)
            DispatchQueue.main.async { [weak self] in
                self?.showInitialMicrophoneAuthorization()
            }
        } else {
            NSApp.setActivationPolicy(.accessory)
            handleMicrophoneAuthorizationResult()
        }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            self?.refreshStatus(rebuildMenu: false)
        }
    }

    private func handleMicrophoneAuthorizationResult() {
        requestMicrophoneAccess { [weak self] granted in
            guard let self else { return }
            if !granted {
                self.updateStatusIcon(
                    symbol: "mic.slash.circle.fill",
                    tooltip: "FamilyRecorder 需要麥克風權限"
                )
            } else if self.currentStatus?.listenerRunning == false {
                _ = self.restartListener()
            }
        }
    }

    private func showInitialMicrophoneAuthorization() {
        let alert = NSAlert()
        alert.messageText = "讓 FamilyRecorder 開始聆聽"
        alert.informativeText =
            "下一步 macOS 會詢問麥克風權限。允許後，FamilyRecorder 才能使用 XVF3800；音訊仍只在這台 Mac 上處理。"
        alert.addButton(withTitle: "繼續並允許麥克風")
        alert.addButton(withTitle: "稍後")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else {
            NSApp.setActivationPolicy(.accessory)
            updateStatusIcon(
                symbol: "mic.slash.circle.fill",
                tooltip: "FamilyRecorder 尚未取得麥克風權限"
            )
            return
        }
        requestMicrophoneAccess { [weak self] granted in
            NSApp.setActivationPolicy(.accessory)
            guard let self else { return }
            if granted {
                if self.currentStatus?.listenerRunning == false {
                    _ = self.restartListener()
                }
            } else {
                self.updateStatusIcon(
                    symbol: "mic.slash.circle.fill",
                    tooltip: "FamilyRecorder 需要麥克風權限"
                )
            }
        }
    }

    func menuWillOpen(_ menu: NSMenu) {
        refreshStatus(rebuildMenu: true)
    }

    private func runRecorderSync(_ arguments: [String]) -> (Int32, String) {
        let process = Process()
        let output = Pipe()
        let error = Pipe()
        process.executableURL = URL(fileURLWithPath: programPath)
        process.arguments = ["--config", configPath] + arguments
        process.standardOutput = output
        process.standardError = error
        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return (1, error.localizedDescription)
        }
        let stdout = String(
            data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8
        ) ?? ""
        let stderr = String(
            data: error.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8
        ) ?? ""
        let combined = [stdout, stderr]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
        return (process.terminationStatus, combined)
    }

    private func runRecorderAsync(
        _ arguments: [String],
        completion: @escaping (Int32, String) -> Void
    ) {
        let process = Process()
        let output = Pipe()
        let error = Pipe()
        process.executableURL = URL(fileURLWithPath: programPath)
        process.arguments = ["--config", configPath] + arguments
        process.standardOutput = output
        process.standardError = error
        runningProcesses.append(process)
        process.terminationHandler = { [weak self, weak process] finished in
            let stdout = String(
                data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8
            ) ?? ""
            let stderr = String(
                data: error.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8
            ) ?? ""
            let combined = [stdout, stderr]
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .joined(separator: "\n")
            DispatchQueue.main.async {
                if let process {
                    self?.runningProcesses.removeAll { $0 === process }
                }
                completion(finished.terminationStatus, combined)
            }
        }
        do {
            try process.run()
        } catch {
            runningProcesses.removeAll { $0 === process }
            completion(1, error.localizedDescription)
        }
    }

    private func refreshStatus(rebuildMenu: Bool) {
        let result = runRecorderSync(["menu-status"])
        guard result.0 == 0, let data = result.1.data(using: .utf8) else {
            updateStatusIcon(symbol: "exclamationmark.triangle.fill", tooltip: "FamilyRecorder 無法讀取狀態")
            if rebuildMenu {
                buildErrorMenu(result.1)
            }
            return
        }
        do {
            currentStatus = try JSONDecoder().decode(RecorderStatus.self, from: data)
            guard let status = currentStatus else { return }
            let symbol: String
            if let name = enrollingSpeakerName {
                symbol = "person.2.fill"
                updateStatusIcon(symbol: symbol, tooltip: "正在建立 \(name) 的聲音樣本")
                if rebuildMenu {
                    buildMenu(status)
                }
                return
            } else if let download = downloadingWhisperModel {
                symbol = "arrow.down.circle.fill"
                updateStatusIcon(symbol: symbol, tooltip: "正在下載 \(download.displayName)")
                if rebuildMenu {
                    buildMenu(status)
                }
                return
            } else if !status.listenerRunning {
                symbol = "exclamationmark.triangle.fill"
            } else if status.paused {
                symbol = "pause.circle.fill"
            } else {
                symbol = "waveform.circle.fill"
            }
            let tooltip = status.listenerRunning ? status.pauseLabel : "錄音服務未執行"
            updateStatusIcon(symbol: symbol, tooltip: tooltip)
            if rebuildMenu {
                buildMenu(status)
            }
        } catch {
            updateStatusIcon(symbol: "exclamationmark.triangle.fill", tooltip: "FamilyRecorder 狀態格式錯誤")
            if rebuildMenu {
                buildErrorMenu(error.localizedDescription)
            }
        }
    }

    private func updateStatusIcon(symbol: String, tooltip: String) {
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: symbol, accessibilityDescription: tooltip)
            button.image?.isTemplate = true
            button.toolTip = tooltip
        }
    }

    private func item(
        _ title: String,
        action: Selector? = nil,
        representedObject: Any? = nil,
        enabled: Bool = true
    ) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        item.representedObject = representedObject
        item.isEnabled = enabled
        return item
    }

    private func buildErrorMenu(_ message: String) {
        menu.removeAllItems()
        menu.addItem(item("⚠️ 無法讀取 FamilyRecorder", enabled: false))
        if !message.isEmpty {
            menu.addItem(item(message, enabled: false))
        }
        menu.addItem(.separator())
        menu.addItem(item("重新讀取", action: #selector(refreshFromMenu)))
        menu.addItem(item("解除安裝 FamilyRecorder…", action: #selector(openUninstaller)))
        menu.addItem(item("結束選單列程式", action: #selector(quitMenuBar)))
    }

    private func buildMenu(_ status: RecorderStatus) {
        menu.removeAllItems()
        let serviceStatus = status.listenerRunning ? status.pauseLabel : "⚠️ 錄音服務未執行"
        menu.addItem(item(serviceStatus, enabled: false))
        menu.addItem(
            item(
                "Whisper：\(status.currentWhisperModel)　摘要：\(status.summaryModel.isEmpty ? "帳號預設" : status.summaryModel)",
                enabled: false
            )
        )
        if status.speakerMembers.isEmpty {
            menu.addItem(item("家庭人別：尚未設定", enabled: false))
        } else {
            let enrolled = status.speakerMembers.filter { $0.enrolled }.count
            menu.addItem(
                item("家庭人別：\(status.speakerMembers.count) 人 · 已註冊 \(enrolled) 人", enabled: false)
            )
        }
        menu.addItem(
            item(
                status.directionEnabled
                    ? "聲音方向：已開啟 · 正前方校準 \(Int(status.directionFrontAngleDegrees.rounded()))°"
                    : "聲音方向：已關閉",
                enabled: false
            )
        )
        menu.addItem(item("常用字詞：\(status.commonTerms.count) 個", enabled: false))
        menu.addItem(.separator())

        if status.paused {
            menu.addItem(item("▶︎ 繼續錄音", action: #selector(resumeRecording)))
        } else {
            let pauseMenuItem = item("暫停錄音")
            let pauseMenu = NSMenu()
            pauseMenu.addItem(item("15 分鐘", action: #selector(pause15Minutes)))
            pauseMenu.addItem(item("1 小時", action: #selector(pauseOneHour)))
            pauseMenu.addItem(item("直到我手動恢復", action: #selector(pauseIndefinitely)))
            pauseMenuItem.submenu = pauseMenu
            menu.addItem(pauseMenuItem)
        }

        let openItem = item("打開…")
        let openMenu = NSMenu()
        openMenu.addItem(item("今天的逐字稿", action: #selector(openPath), representedObject: status.todayTranscript))
        openMenu.addItem(item("今天的摘要", action: #selector(openPath), representedObject: status.todaySummary))
        openMenu.addItem(.separator())
        openMenu.addItem(item("全部資料", action: #selector(openPath), representedObject: status.dataDir))
        openMenu.addItem(item("逐字稿資料夾", action: #selector(openPath), representedObject: status.transcriptDir))
        openMenu.addItem(item("摘要資料夾", action: #selector(openPath), representedObject: status.summaryDir))
        openMenu.addItem(item("錄音資料夾", action: #selector(openPath), representedObject: status.audioDir))
        openMenu.addItem(item("Log 資料夾", action: #selector(openPath), representedObject: status.logDir))
        openMenu.addItem(
            item("聲音特徵資料夾", action: #selector(openPath), representedObject: status.speakerProfilesDir)
        )
        openMenu.addItem(item("設定檔", action: #selector(openPath), representedObject: status.configPath))
        openItem.submenu = openMenu
        menu.addItem(openItem)

        let modelItem = item("更換模型")
        let modelMenu = NSMenu()
        let whisperItem = item("本機 Whisper")
        let whisperMenu = NSMenu()
        if status.whisperModels.isEmpty {
            whisperMenu.addItem(item("沒有找到已下載的模型", enabled: false))
        } else {
            for model in status.whisperModels {
                let modelItem = item(
                    model.name,
                    action: #selector(selectWhisperModel),
                    representedObject: model.path
                )
                if model.path == status.currentWhisperModelPath {
                    modelItem.state = .on
                }
                whisperMenu.addItem(modelItem)
            }
        }
        whisperMenu.addItem(.separator())
        let downloadItem = item("下載其他模型…")
        let downloadMenu = NSMenu()
        if let download = downloadingWhisperModel {
            downloadMenu.addItem(item("正在下載 \(download.displayName)…", enabled: false))
        } else {
            for category in ["標準模型", "量化省空間", "舊版相容"] {
                let categoryItem = item(category)
                let categoryMenu = NSMenu()
                for model in status.downloadableWhisperModels where model.category == category {
                    let suffix = model.installed ? "（已安裝）" : ""
                    let modelItem = item(
                        "\(model.displayName) · \(model.sizeLabel)\(suffix)",
                        action: model.installed ? nil : #selector(downloadWhisperModel),
                        representedObject: model,
                        enabled: !model.installed
                    )
                    modelItem.toolTip = model.description
                    if model.installed {
                        modelItem.state = .on
                    }
                    categoryMenu.addItem(modelItem)
                }
                categoryItem.submenu = categoryMenu
                downloadMenu.addItem(categoryItem)
            }
        }
        downloadItem.submenu = downloadMenu
        whisperMenu.addItem(downloadItem)
        whisperItem.submenu = whisperMenu
        modelMenu.addItem(whisperItem)

        let summaryItem = item("ChatGPT 摘要")
        let summaryMenu = NSMenu()
        let accountDefault = item("使用帳號預設", action: #selector(useDefaultSummaryModel))
        accountDefault.state = status.summaryModel.isEmpty ? .on : .off
        summaryMenu.addItem(accountDefault)
        let customTitle = status.summaryModel.isEmpty ? "輸入自訂模型…" : "自訂：\(status.summaryModel)…"
        let custom = item(customTitle, action: #selector(chooseSummaryModel))
        custom.state = status.summaryModel.isEmpty ? .off : .on
        summaryMenu.addItem(custom)
        summaryMenu.addItem(.separator())
        summaryMenu.addItem(item("編輯摘要 Prompt…", action: #selector(editSummaryPrompt)))
        summaryMenu.addItem(item("恢復內建摘要 Prompt…", action: #selector(resetSummaryPrompt)))
        summaryItem.submenu = summaryMenu
        modelMenu.addItem(summaryItem)
        modelItem.submenu = modelMenu
        menu.addItem(modelItem)

        let termsItem = item("常用字詞校正")
        let termsMenu = NSMenu()
        if status.commonTerms.isEmpty {
            termsMenu.addItem(item("尚未設定", enabled: false))
        } else {
            for term in status.commonTerms {
                termsMenu.addItem(item("✓ \(term)", enabled: false))
            }
        }
        termsMenu.addItem(.separator())
        termsMenu.addItem(item("新增／移除常用字詞…", action: #selector(editCommonTerms)))
        termsMenu.addItem(
            item("辨識前提示，並保守校正單一字差", enabled: false)
        )
        termsItem.submenu = termsMenu
        menu.addItem(termsItem)

        let familyItem = item("家庭成員與人聲")
        let familyMenu = NSMenu()
        if status.speakerMembers.isEmpty {
            familyMenu.addItem(item("尚未設定成員", enabled: false))
        } else {
            for member in status.speakerMembers {
                let memberItem = item(member.enrolled ? "✓ \(member.name)" : "○ \(member.name)（未註冊）")
                let memberMenu = NSMenu()
                memberMenu.addItem(
                    item(
                        member.enrolled ? "重新錄製聲音樣本…" : "錄製聲音樣本…",
                        action: #selector(enrollSpeaker),
                        representedObject: member.name,
                        enabled: enrollingSpeakerName == nil
                    )
                )
                memberMenu.addItem(
                    item(
                        "刪除聲音樣本",
                        action: #selector(deleteSpeakerProfile),
                        representedObject: member.name,
                        enabled: member.enrolled && enrollingSpeakerName == nil
                    )
                )
                memberItem.submenu = memberMenu
                familyMenu.addItem(memberItem)
            }
        }
        familyMenu.addItem(.separator())
        familyMenu.addItem(
            item(
                "設定家庭成員…",
                action: #selector(editSpeakerMembers),
                enabled: enrollingSpeakerName == nil
            )
        )
        familyMenu.addItem(
            item(
                "說明：僅為本機近似判斷，不是身分驗證",
                enabled: false
            )
        )
        familyItem.submenu = familyMenu
        menu.addItem(familyItem)

        let directionItem = item("聲音方向")
        let directionMenu = NSMenu()
        let directionToggle = item(
            status.directionEnabled ? "關閉方向判斷" : "開啟方向判斷",
            action: #selector(toggleDirection)
        )
        directionMenu.addItem(directionToggle)
        directionMenu.addItem(
            item(
                "測試目前方向…",
                action: #selector(probeDirection),
                enabled: status.directionEnabled
            )
        )
        directionMenu.addItem(
            item(
                "把目前位置校準為正前方…",
                action: #selector(calibrateDirection),
                enabled: status.directionEnabled
            )
        )
        directionMenu.addItem(.separator())
        directionMenu.addItem(
            item("方向只作為音色人別的輔助線索，不是身分確認", enabled: false)
        )
        directionItem.submenu = directionMenu
        menu.addItem(directionItem)

        menu.addItem(buildCalendarMenu(status))

        menu.addItem(.separator())
        menu.addItem(item("立即整理今天", action: #selector(summarizeToday)))
        menu.addItem(item("重新啟動錄音服務", action: #selector(restartListenerFromMenu)))
        menu.addItem(item("檢查系統狀態…", action: #selector(runDoctor)))
        menu.addItem(item("重新讀取狀態", action: #selector(refreshFromMenu)))
        menu.addItem(.separator())
        menu.addItem(item("解除安裝 FamilyRecorder…", action: #selector(openUninstaller)))
        menu.addItem(item("結束選單列程式", action: #selector(quitMenuBar)))
    }

    private func buildCalendarMenu(_ status: RecorderStatus) -> NSMenuItem {
        let calendarItem = item("Google Calendar")
        let calendarMenu = NSMenu()
        let defaultName = status.calendarDefaultName.isEmpty ? "尚未選擇" : status.calendarDefaultName
        calendarMenu.addItem(
            item(
                status.calendarEnabled
                    ? "已開啟 · 預設：\(defaultName)"
                    : "尚未開啟 · 預設：\(defaultName)",
                enabled: false
            )
        )
        calendarMenu.addItem(
            item("連接／選擇預設 Google Calendar…", action: #selector(chooseDefaultCalendar))
        )
        if !status.calendarDefaultID.isEmpty {
            calendarMenu.addItem(
                item(
                    status.calendarEnabled ? "暫停產生候選事件" : "開啟候選事件",
                    action: #selector(toggleCalendarCandidates)
                )
            )
        }

        let mappingItem = item("家庭成員日曆對應")
        let mappingMenu = NSMenu()
        if status.speakerMembers.isEmpty {
            mappingMenu.addItem(item("請先設定家庭成員", enabled: false))
        } else if availableGoogleCalendars.isEmpty {
            mappingMenu.addItem(item("請先連接 Google Calendar", enabled: false))
        } else {
            for member in status.speakerMembers {
                let memberItem = item(member.name)
                let memberMenu = NSMenu()
                let assigned = Set(status.calendarMemberIDs[member.name] ?? [])
                let memberDefault = status.calendarMemberDefaultIDs[member.name]
                for calendar in availableGoogleCalendars {
                    let choice = MemberCalendarChoice(
                        member: member.name,
                        calendarID: calendar.calendarIdentifier
                    )
                    let calendarItem = item(
                        calendarDisplayName(calendar),
                        action: #selector(toggleMemberCalendar),
                        representedObject: choice
                    )
                    calendarItem.state = assigned.contains(calendar.calendarIdentifier) ? .on : .off
                    memberMenu.addItem(calendarItem)
                }
                if !assigned.isEmpty {
                    memberMenu.addItem(.separator())
                    memberMenu.addItem(item("此成員的預設日曆", enabled: false))
                    for calendar in availableGoogleCalendars
                    where assigned.contains(calendar.calendarIdentifier) {
                        let choice = MemberCalendarChoice(
                            member: member.name,
                            calendarID: calendar.calendarIdentifier
                        )
                        let defaultItem = item(
                            calendarDisplayName(calendar),
                            action: #selector(selectMemberDefaultCalendar),
                            representedObject: choice
                        )
                        defaultItem.state = memberDefault == calendar.calendarIdentifier ? .on : .off
                        memberMenu.addItem(defaultItem)
                    }
                }
                memberItem.submenu = memberMenu
                mappingMenu.addItem(memberItem)
            }
        }
        mappingItem.submenu = mappingMenu
        calendarMenu.addItem(mappingItem)

        calendarMenu.addItem(.separator())
        let pendingItem = item("待確認事件（\(status.calendarPendingEvents.count)）")
        let pendingMenu = NSMenu()
        if status.calendarPendingEvents.isEmpty {
            pendingMenu.addItem(item("目前沒有候選事件", enabled: false))
        } else {
            for event in status.calendarPendingEvents {
                let eventItem = item("\(calendarEventTime(event)) · \(event.title)")
                let eventMenu = NSMenu()
                if !event.memberName.isEmpty {
                    eventMenu.addItem(item("建議成員：\(event.memberName)", enabled: false))
                }
                eventMenu.addItem(
                    item(
                        "確認並加入建議日曆…",
                        action: #selector(confirmCalendarEvent),
                        representedObject: NSNumber(value: event.id)
                    )
                )
                eventMenu.addItem(
                    item(
                        "選擇其他 Google Calendar…",
                        action: #selector(confirmCalendarEventWithChoice),
                        representedObject: NSNumber(value: event.id)
                    )
                )
                eventMenu.addItem(
                    item(
                        "略過",
                        action: #selector(dismissCalendarEvent),
                        representedObject: NSNumber(value: event.id)
                    )
                )
                eventItem.submenu = eventMenu
                pendingMenu.addItem(eventItem)
            }
        }
        pendingItem.submenu = pendingMenu
        calendarMenu.addItem(pendingItem)
        calendarMenu.addItem(.separator())
        calendarMenu.addItem(item("AI 只建立候選項目；確認後才寫入日曆", enabled: false))
        calendarItem.submenu = calendarMenu
        return calendarItem
    }

    private func runSimpleAction(_ arguments: [String], successTitle: String) {
        runRecorderAsync(arguments) { [weak self] status, output in
            self?.refreshStatus(rebuildMenu: true)
            if status != 0 {
                self?.showAlert(title: "操作失敗", message: output)
            } else if !successTitle.isEmpty {
                self?.showAlert(title: successTitle, message: output)
            }
        }
    }

    @objc private func pause15Minutes() {
        runSimpleAction(["pause", "--minutes", "15"], successTitle: "錄音已暫停 15 分鐘")
    }

    @objc private func pauseOneHour() {
        runSimpleAction(["pause", "--minutes", "60"], successTitle: "錄音已暫停 1 小時")
    }

    @objc private func pauseIndefinitely() {
        runSimpleAction(["pause"], successTitle: "錄音已暫停")
    }

    @objc private func resumeRecording() {
        runSimpleAction(["resume"], successTitle: "錄音已恢復")
    }

    @objc private func openPath(_ sender: NSMenuItem) {
        guard let path = sender.representedObject as? String else { return }
        var url = URL(fileURLWithPath: path)
        if !FileManager.default.fileExists(atPath: path) {
            url.deleteLastPathComponent()
        }
        NSWorkspace.shared.open(url)
    }

    @objc private func selectWhisperModel(_ sender: NSMenuItem) {
        guard let path = sender.representedObject as? String else { return }
        let alert = NSAlert()
        alert.messageText = "切換本機 Whisper 模型？"
        alert.informativeText = "錄音服務會重新啟動，當下正在錄製的 30 秒片段可能不會保留。"
        alert.addButton(withTitle: "切換")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runRecorderAsync(["set-whisper-model", "--path", path]) { [weak self] status, output in
            guard status == 0 else {
                self?.showAlert(title: "模型切換失敗", message: output)
                return
            }
            let restart = self?.restartListener() ?? (1, "無法重新啟動錄音服務")
            self?.refreshStatus(rebuildMenu: true)
            if restart.0 != 0 {
                self?.showAlert(title: "模型已儲存，但服務重啟失敗", message: restart.1)
            }
        }
    }

    @objc private func downloadWhisperModel(_ sender: NSMenuItem) {
        guard let model = sender.representedObject as? DownloadableWhisperModel else { return }
        let alert = NSAlert()
        alert.messageText = "下載並切換到 \(model.displayName)？"
        alert.informativeText =
            "預估下載容量：\(model.sizeLabel)\n\(model.description)。下載期間仍使用目前模型錄音；完成後才會切換並重新啟動錄音服務。既有模型不會刪除。"
        alert.addButton(withTitle: "下載並切換")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        downloadingWhisperModel = model
        updateStatusIcon(symbol: "arrow.down.circle.fill", tooltip: "正在下載 \(model.displayName)")
        refreshStatus(rebuildMenu: true)
        runRecorderAsync(["download-whisper-model", "--model", model.name]) {
            [weak self] status, output in
            guard let self else { return }
            self.downloadingWhisperModel = nil
            guard status == 0 else {
                self.refreshStatus(rebuildMenu: true)
                self.showAlert(title: "模型下載失敗", message: output)
                return
            }
            let restart = self.restartListener()
            self.refreshStatus(rebuildMenu: true)
            if restart.0 == 0 {
                self.showAlert(
                    title: "模型已下載並切換",
                    message: "目前使用 \(model.displayName)。原有模型仍保留，可隨時切回。"
                )
            } else {
                self.showAlert(title: "模型已切換，但服務重啟失敗", message: restart.1)
            }
        }
    }

    @objc private func useDefaultSummaryModel() {
        runSimpleAction(["set-summary-model", "--model", ""], successTitle: "已使用 ChatGPT 帳號預設模型")
    }

    @objc private func editSummaryPrompt() {
        let alert = NSAlert()
        alert.messageText = "編輯 ChatGPT 摘要 Prompt"
        alert.informativeText =
            "請描述每天希望如何整理逐字稿。只上傳文字、不得捏造內容，以及時間／人別／方向等保護規則會由 FamilyRecorder 固定附加。"
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 560, height: 300))
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.borderType = .bezelBorder
        let textView = NSTextView(frame: scroll.bounds)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.font = NSFont.systemFont(ofSize: 13)
        textView.string = currentStatus?.summaryPrompt ?? ""
        scroll.documentView = textView
        alert.accessoryView = scroll
        alert.addButton(withTitle: "儲存")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let prompt = textView.string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            showAlert(title: "摘要 Prompt 不可空白", message: "請輸入摘要需求，或使用恢復內建 Prompt。")
            return
        }
        runSimpleAction(
            ["set-summary-prompt", "--prompt", prompt],
            successTitle: "摘要 Prompt 已儲存"
        )
    }

    @objc private func resetSummaryPrompt() {
        let alert = NSAlert()
        alert.messageText = "恢復內建摘要 Prompt？"
        alert.informativeText = "目前自訂內容會被內建的繁體中文家庭摘要格式取代。"
        alert.addButton(withTitle: "恢復預設")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runSimpleAction(["reset-summary-prompt"], successTitle: "已恢復內建摘要 Prompt")
    }

    private func calendarDisplayName(_ calendar: EKCalendar) -> String {
        "\(calendar.source.title) › \(calendar.title)"
    }

    private func refreshGoogleCalendars() {
        availableGoogleCalendars = eventStore.calendars(for: .event)
            .filter { calendar in
                guard calendar.allowsContentModifications else { return false }
                let source = calendar.source.title.lowercased()
                return calendar.source.sourceType == .calDAV
                    && !source.contains("icloud")
            }
            .sorted { calendarDisplayName($0) < calendarDisplayName($1) }
    }

    private func requestCalendarAccess(completion: @escaping (Bool) -> Void) {
        NSApp.activate(ignoringOtherApps: true)
        let finished: (Bool, Error?) -> Void = { [weak self] granted, _ in
            DispatchQueue.main.async {
                if granted {
                    self?.refreshGoogleCalendars()
                }
                completion(granted)
            }
        }
        if #available(macOS 14.0, *) {
            eventStore.requestFullAccessToEvents(completion: finished)
        } else {
            eventStore.requestAccess(to: .event, completion: finished)
        }
    }

    private func showCalendarPermissionAlert() {
        let alert = NSAlert()
        alert.messageText = "FamilyRecorder 需要行事曆權限"
        alert.informativeText =
            "請在「系統設定 → 隱私權與安全性 → 行事曆」允許 FamilyRecorder，才能列出日曆並在確認後建立事件。"
        alert.addButton(withTitle: "打開系統設定")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertFirstButtonReturn,
           let url = URL(
               string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Calendars"
           )
        {
            NSWorkspace.shared.open(url)
        }
    }

    private func showMissingGoogleCalendarAlert() {
        let alert = NSAlert()
        alert.messageText = "找不到可寫入的 Google Calendar"
        alert.informativeText =
            "請先在 macOS「系統設定 → Internet 帳號」加入 Google 帳號並開啟行事曆同步，再回來重試。"
        alert.addButton(withTitle: "打開 Internet 帳號")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertFirstButtonReturn,
           let url = URL(string: "x-apple.systempreferences:com.apple.preferences.internetaccounts")
        {
            NSWorkspace.shared.open(url)
        }
    }

    private func chooseCalendar(title: String) -> EKCalendar? {
        guard !availableGoogleCalendars.isEmpty else {
            showMissingGoogleCalendarAlert()
            return nil
        }
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = "只列出 macOS 行事曆中可寫入的 Google／CalDAV 日曆。"
        let popup = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 460, height: 28))
        for calendar in availableGoogleCalendars {
            popup.addItem(withTitle: calendarDisplayName(calendar))
        }
        alert.accessoryView = popup
        alert.addButton(withTitle: "選擇")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return nil }
        return availableGoogleCalendars[popup.indexOfSelectedItem]
    }

    @objc private func chooseDefaultCalendar() {
        requestCalendarAccess { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.showCalendarPermissionAlert()
                return
            }
            guard let calendar = self.chooseCalendar(title: "選擇預設 Google Calendar") else {
                return
            }
            self.runSimpleAction(
                [
                    "set-calendar-default",
                    "--calendar-id", calendar.calendarIdentifier,
                    "--calendar-name", self.calendarDisplayName(calendar),
                ],
                successTitle: "Google Calendar 已連接"
            )
        }
    }

    @objc private func toggleCalendarCandidates() {
        let enabled = !(currentStatus?.calendarEnabled ?? false)
        runSimpleAction(
            ["set-calendar-enabled", "--enabled", enabled ? "true" : "false"],
            successTitle: enabled ? "Google Calendar 候選事件已開啟" : "候選事件已暫停"
        )
    }

    @objc private func toggleMemberCalendar(_ sender: NSMenuItem) {
        guard let choice = sender.representedObject as? MemberCalendarChoice else { return }
        let assigned = currentStatus?.calendarMemberIDs[choice.member] ?? []
        runSimpleAction(
            [
                "set-member-calendar",
                "--member", choice.member,
                "--calendar-id", choice.calendarID,
                "--calendar-name", availableGoogleCalendars.first {
                    $0.calendarIdentifier == choice.calendarID
                }.map(calendarDisplayName) ?? "",
                "--enabled", assigned.contains(choice.calendarID) ? "false" : "true",
            ],
            successTitle: "家庭成員日曆對應已更新"
        )
    }

    @objc private func selectMemberDefaultCalendar(_ sender: NSMenuItem) {
        guard let choice = sender.representedObject as? MemberCalendarChoice else { return }
        runSimpleAction(
            [
                "set-member-calendar-default",
                "--member", choice.member,
                "--calendar-id", choice.calendarID,
            ],
            successTitle: "家庭成員預設日曆已更新"
        )
    }

    private func pendingCalendarEvent(_ sender: NSMenuItem) -> PendingCalendarEvent? {
        guard let number = sender.representedObject as? NSNumber else { return nil }
        return currentStatus?.calendarPendingEvents.first { $0.id == number.intValue }
    }

    private func calendarEventTime(_ event: PendingCalendarEvent) -> String {
        if event.allDay {
            return event.startsAt
        }
        guard let date = ISO8601DateFormatter().date(from: event.startsAt) else {
            return event.startsAt
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_TW")
        formatter.dateFormat = "M/d HH:mm"
        return formatter.string(from: date)
    }

    private func dates(for event: PendingCalendarEvent) -> (Date, Date)? {
        if event.allDay {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.timeZone = .current
            formatter.dateFormat = "yyyy-MM-dd"
            guard let start = formatter.date(from: event.startsAt),
                  let end = formatter.date(from: event.endsAt)
            else { return nil }
            return (start, end)
        }
        let formatter = ISO8601DateFormatter()
        guard let start = formatter.date(from: event.startsAt),
              let end = formatter.date(from: event.endsAt)
        else { return nil }
        return (start, end)
    }

    private func suggestedCalendar(for event: PendingCalendarEvent) -> EKCalendar? {
        guard let status = currentStatus else { return nil }
        let memberDefault = status.calendarMemberDefaultIDs[event.memberName]
        let calendarID = (!event.suggestedCalendarID.isEmpty ? event.suggestedCalendarID : nil)
            ?? memberDefault
            ?? (!status.calendarDefaultID.isEmpty ? status.calendarDefaultID : nil)
        return availableGoogleCalendars.first { $0.calendarIdentifier == calendarID }
    }

    @objc private func confirmCalendarEvent(_ sender: NSMenuItem) {
        guard let event = pendingCalendarEvent(sender) else { return }
        requestCalendarAccess { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.showCalendarPermissionAlert()
                return
            }
            guard let calendar = self.suggestedCalendar(for: event)
                ?? self.chooseCalendar(title: "選擇要加入的 Google Calendar")
            else { return }
            self.createCalendarEvent(event, in: calendar)
        }
    }

    @objc private func confirmCalendarEventWithChoice(_ sender: NSMenuItem) {
        guard let event = pendingCalendarEvent(sender) else { return }
        requestCalendarAccess { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.showCalendarPermissionAlert()
                return
            }
            guard let calendar = self.chooseCalendar(title: "選擇要加入的 Google Calendar") else {
                return
            }
            self.createCalendarEvent(event, in: calendar)
        }
    }

    private func createCalendarEvent(_ candidate: PendingCalendarEvent, in calendar: EKCalendar) {
        guard let (startDate, endDate) = dates(for: candidate) else {
            showAlert(title: "事件時間格式錯誤", message: "請略過這個候選事件並手動建立。")
            return
        }
        let alert = NSAlert()
        alert.messageText = "加入 Google Calendar？"
        let member = candidate.memberName.isEmpty ? "未指定" : candidate.memberName
        alert.informativeText =
            "事件：\(candidate.title)\n時間：\(calendarEventTime(candidate))\n成員：\(member)\n日曆：\(calendarDisplayName(calendar))\n\n只有按下確認後才會真正建立。"
        alert.addButton(withTitle: "確認建立")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        let event = EKEvent(eventStore: eventStore)
        event.calendar = calendar
        event.title = candidate.title
        event.startDate = startDate
        event.endDate = endDate
        event.isAllDay = candidate.allDay
        let sourceNote = "由 FamilyRecorder 每日摘要產生，並經使用者確認。"
        event.notes = candidate.notes.isEmpty ? sourceNote : "\(sourceNote)\n\(candidate.notes)"
        do {
            try eventStore.save(event, span: .thisEvent, commit: true)
        } catch {
            showAlert(title: "無法建立行事曆事件", message: error.localizedDescription)
            return
        }
        runRecorderAsync(
            [
                "calendar-event-created",
                "--id", String(candidate.id),
                "--external-id", event.eventIdentifier ?? "",
            ]
        ) { [weak self] status, output in
            self?.refreshStatus(rebuildMenu: true)
            self?.showAlert(
                title: status == 0 ? "已加入 Google Calendar" : "事件已建立，但狀態更新失敗",
                message: status == 0 ? self?.calendarDisplayName(calendar) ?? output : output
            )
        }
    }

    @objc private func dismissCalendarEvent(_ sender: NSMenuItem) {
        guard let event = pendingCalendarEvent(sender) else { return }
        let alert = NSAlert()
        alert.messageText = "略過「\(event.title)」？"
        alert.informativeText = "這個候選項目不會建立到 Google Calendar。"
        alert.addButton(withTitle: "略過")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runSimpleAction(
            ["dismiss-calendar-event", "--id", String(event.id)],
            successTitle: "候選事件已略過"
        )
    }

    @objc private func editSpeakerMembers() {
        let alert = NSAlert()
        alert.messageText = "設定家庭成員"
        alert.informativeText =
            "每行一位，最多 8 人。移除成員時，該成員存在本機的聲音特徵也會一併刪除。"
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 420, height: 145))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        let textView = NSTextView(frame: scroll.bounds)
        textView.isVerticallyResizable = true
        textView.autoresizingMask = [.width]
        textView.font = NSFont.systemFont(ofSize: 14)
        textView.string = currentStatus?.speakerMembers.map { $0.name }.joined(separator: "\n") ?? ""
        scroll.documentView = textView
        alert.accessoryView = scroll
        alert.addButton(withTitle: "儲存")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let names = textView.string
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        var arguments = ["set-speakers"]
        for name in names {
            arguments.append(contentsOf: ["--name", name])
        }
        runRecorderAsync(arguments) { [weak self] status, output in
            guard status == 0 else {
                self?.showAlert(title: "家庭成員設定失敗", message: output)
                return
            }
            let restart = self?.restartListener() ?? (1, "無法重新啟動錄音服務")
            self?.refreshStatus(rebuildMenu: true)
            if restart.0 != 0 {
                self?.showAlert(title: "設定已儲存，但錄音服務重啟失敗", message: restart.1)
            }
        }
    }

    @objc private func editCommonTerms() {
        let alert = NSAlert()
        alert.messageText = "設定常用字詞"
        alert.informativeText =
            "每行一個姓名或專有名詞，最多 100 個。這些字詞只在本機提供給 Whisper，並保守校正只有一個字不同且沒有歧義的結果。"
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 420, height: 180))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        let textView = NSTextView(frame: scroll.bounds)
        textView.isVerticallyResizable = true
        textView.autoresizingMask = [.width]
        textView.font = NSFont.systemFont(ofSize: 14)
        textView.string = currentStatus?.commonTerms.joined(separator: "\n") ?? ""
        scroll.documentView = textView
        alert.accessoryView = scroll
        alert.addButton(withTitle: "儲存")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let terms = textView.string
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        var arguments = ["set-common-terms"]
        for term in terms {
            arguments.append(contentsOf: ["--term", term])
        }
        runRecorderAsync(arguments) { [weak self] status, output in
            guard status == 0 else {
                self?.showAlert(title: "常用字詞設定失敗", message: output)
                return
            }
            let restart = self?.restartListener() ?? (1, "無法重新啟動錄音服務")
            self?.refreshStatus(rebuildMenu: true)
            if restart.0 != 0 {
                self?.showAlert(title: "設定已儲存，但錄音服務重啟失敗", message: restart.1)
            }
        }
    }

    @objc private func toggleDirection() {
        let enabled = !(currentStatus?.directionEnabled ?? true)
        runRecorderAsync(
            ["set-direction-enabled", "--enabled", enabled ? "true" : "false"]
        ) { [weak self] status, output in
            guard let self else { return }
            guard status == 0 else {
                self.showAlert(title: "方向設定失敗", message: output)
                return
            }
            let restart = self.restartListener()
            self.refreshStatus(rebuildMenu: true)
            self.showAlert(
                title: enabled ? "方向判斷已開啟" : "方向判斷已關閉",
                message: restart.0 == 0 ? output : "\(output)\n\(restart.1)"
            )
        }
    }

    @objc private func probeDirection() {
        runRecorderAsync(["probe-direction", "--seconds", "2"]) { [weak self] status, output in
            self?.showAlert(
                title: status == 0 ? "目前聲音方向" : "方向測試失敗",
                message: output
            )
        }
    }

    @objc private func calibrateDirection() {
        let alert = NSAlert()
        alert.messageText = "校準 FamilyRecorder 的正前方"
        alert.informativeText =
            "請站在你希望定義為「正前方」的位置。按下開始約 2 秒後，請只有一個人持續自然說話 4 秒。錄音服務會暫停，校準完成後自動恢復。"
        alert.addButton(withTitle: "開始校準")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        let shouldResume = !(currentStatus?.paused ?? false)
        if shouldResume {
            let pause = runRecorderSync(["pause"])
            guard pause.0 == 0 else {
                showAlert(title: "無法暫停錄音服務", message: pause.1)
                return
            }
        }
        updateStatusIcon(symbol: "location.circle.fill", tooltip: "正在校準正前方")
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            guard let self else { return }
            self.runRecorderAsync(["calibrate-direction", "--seconds", "4"]) {
                [weak self] status, output in
                guard let self else { return }
                if shouldResume {
                    _ = self.runRecorderSync(["resume"])
                }
                let restart = self.restartListener()
                self.refreshStatus(rebuildMenu: true)
                if status == 0 && restart.0 == 0 {
                    self.showAlert(title: "正前方校準完成", message: output)
                } else {
                    let details = [output, restart.1]
                        .filter { !$0.isEmpty }
                        .joined(separator: "\n")
                    self.showAlert(title: "方向校準失敗", message: details)
                }
            }
        }
    }

    @objc private func enrollSpeaker(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String else { return }
        requestMicrophoneAccess { [weak self] granted in
            guard let self else { return }
            if granted {
                self.beginSpeakerEnrollment(name)
            } else {
                self.showMicrophonePermissionAlert()
            }
        }
    }

    private func requestMicrophoneAccess(completion: @escaping (Bool) -> Void) {
        NSApp.activate(ignoringOtherApps: true)
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            completion(true)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                DispatchQueue.main.async {
                    completion(granted)
                }
            }
        case .denied, .restricted:
            completion(false)
        @unknown default:
            completion(false)
        }
    }

    private func showMicrophonePermissionAlert() {
        let alert = NSAlert()
        alert.messageText = "FamilyRecorder 需要麥克風權限"
        alert.informativeText =
            "請在「系統設定 → 隱私權與安全性 → 麥克風」允許 FamilyRecorder，然後重新錄製聲音樣本。"
        alert.addButton(withTitle: "打開系統設定")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertFirstButtonReturn,
           let url = URL(
               string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
           )
        {
            NSWorkspace.shared.open(url)
        }
    }

    private func beginSpeakerEnrollment(_ name: String) {
        let alert = NSAlert()
        alert.messageText = "建立 \(name) 的聲音樣本"
        alert.informativeText =
            "按下開始後會出現持續顯示的朗讀視窗。先有 2 秒準備時間，接著請靠近平常的收音位置，自然連續說話 15 秒。\n\n錄音只用來產生本機聲音特徵，原始註冊音訊不會保存。"
        alert.addButton(withTitle: "開始")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        let shouldResume = !(currentStatus?.paused ?? false)
        if shouldResume {
            let pause = runRecorderSync(["pause"])
            guard pause.0 == 0 else {
                showAlert(title: "無法暫停錄音服務", message: pause.1)
                return
            }
        }
        enrollingSpeakerName = name
        showEnrollmentPanel(for: name)
        updateStatusIcon(symbol: "person.2.fill", tooltip: "正在建立 \(name) 的聲音樣本")
        refreshStatus(rebuildMenu: true)
        runRecorderAsync(["enroll-speaker", "--name", name, "--seconds", "15", "--delay", "2"]) {
            [weak self] status, output in
            guard let self else { return }
            if shouldResume {
                _ = self.runRecorderSync(["resume"])
            }
            self.closeEnrollmentPanel()
            self.enrollingSpeakerName = nil
            self.refreshStatus(rebuildMenu: true)
            self.showAlert(
                title: status == 0 ? "聲音樣本已建立" : "聲音樣本建立失敗",
                message: output
            )
        }
    }

    private func showEnrollmentPanel(for name: String) {
        closeEnrollmentPanel()

        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 360),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )
        panel.title = "FamilyRecorder 聲音樣本"
        panel.level = .floating
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.standardWindowButton(.closeButton)?.isHidden = true
        panel.standardWindowButton(.miniaturizeButton)?.isHidden = true
        panel.standardWindowButton(.zoomButton)?.isHidden = true

        let content = NSView()
        content.translatesAutoresizingMaskIntoConstraints = false
        panel.contentView = content

        let title = NSTextField(labelWithString: "請 \(name) 持續朗讀")
        title.font = .boldSystemFont(ofSize: 21)

        let instruction = NSTextField(
            wrappingLabelWithString:
                "請以自然音量、平常說話的速度朗讀。句子唸完後可從頭再唸，直到畫面顯示錄音完成。"
        )
        instruction.font = .systemFont(ofSize: 14)
        instruction.textColor = .secondaryLabelColor

        let sample = NSTextField(
            wrappingLabelWithString:
                "今天是我的聲音樣本，我正在家裡使用 FamilyRecorder。請記住我的聲音，但不需要保存這段錄音。"
        )
        sample.font = .systemFont(ofSize: 18, weight: .medium)
        sample.isSelectable = true
        sample.drawsBackground = true
        sample.backgroundColor = .controlBackgroundColor
        sample.isBezeled = true
        sample.bezelStyle = .roundedBezel

        let status = NSTextField(labelWithString: "")
        status.font = .boldSystemFont(ofSize: 16)
        status.alignment = .center

        let progress = NSProgressIndicator()
        progress.isIndeterminate = false
        progress.minValue = 0
        progress.maxValue = 17
        progress.doubleValue = 0
        progress.controlSize = .regular

        let privacy = NSTextField(
            wrappingLabelWithString:
                "原始註冊音訊不會保存；完成後只留下這台 Mac 上的聲音特徵。"
        )
        privacy.font = .systemFont(ofSize: 12)
        privacy.textColor = .secondaryLabelColor
        privacy.alignment = .center

        let stack = NSStackView(views: [title, instruction, sample, status, progress, privacy])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(stack)

        for view in [title, instruction, sample, status, progress, privacy] {
            view.translatesAutoresizingMaskIntoConstraints = false
            view.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        }
        sample.heightAnchor.constraint(greaterThanOrEqualToConstant: 92).isActive = true
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 24),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: content.bottomAnchor, constant: -24),
        ])

        enrollmentPanel = panel
        enrollmentStatusLabel = status
        enrollmentProgress = progress
        enrollmentStartedAt = Date()
        updateEnrollmentProgress()
        enrollmentTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) {
            [weak self] _ in
            self?.updateEnrollmentProgress()
        }
        panel.center()
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
    }

    private func updateEnrollmentProgress() {
        guard let startedAt = enrollmentStartedAt else { return }
        let elapsed = Date().timeIntervalSince(startedAt)
        enrollmentProgress?.doubleValue = min(17, elapsed)
        if elapsed < 2 {
            let remaining = max(1, Int(ceil(2 - elapsed)))
            enrollmentStatusLabel?.stringValue = "準備中：\(remaining) 秒後開始錄音"
            enrollmentStatusLabel?.textColor = .secondaryLabelColor
        } else if elapsed < 17 {
            let remaining = max(1, Int(ceil(17 - elapsed)))
            enrollmentStatusLabel?.stringValue = "● 正在錄音，剩餘 \(remaining) 秒"
            enrollmentStatusLabel?.textColor = .systemRed
        } else {
            enrollmentStatusLabel?.stringValue = "錄音完成，正在建立聲音特徵…"
            enrollmentStatusLabel?.textColor = .systemBlue
        }
    }

    private func closeEnrollmentPanel() {
        enrollmentTimer?.invalidate()
        enrollmentTimer = nil
        enrollmentStartedAt = nil
        enrollmentPanel?.orderOut(nil)
        enrollmentPanel = nil
        enrollmentStatusLabel = nil
        enrollmentProgress = nil
    }

    @objc private func deleteSpeakerProfile(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String else { return }
        let alert = NSAlert()
        alert.messageText = "刪除 \(name) 的聲音樣本？"
        alert.informativeText = "只會刪除本機聲音特徵；家庭成員姓名仍保留，可稍後重新錄製。"
        alert.addButton(withTitle: "刪除")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runSimpleAction(
            ["delete-speaker-profile", "--name", name],
            successTitle: "聲音樣本已刪除"
        )
    }

    @objc private func chooseSummaryModel() {
        let alert = NSAlert()
        alert.messageText = "自訂 ChatGPT 摘要模型"
        alert.informativeText = "請輸入你的 ChatGPT／Codex 帳號可使用的模型名稱。留空代表帳號預設。"
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 360, height: 24))
        field.placeholderString = "例如：帳號可用的 Codex 模型名稱"
        field.stringValue = currentStatus?.summaryModel ?? ""
        alert.accessoryView = field
        alert.addButton(withTitle: "儲存")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runSimpleAction(
            ["set-summary-model", "--model", field.stringValue],
            successTitle: "摘要模型已更新"
        )
    }

    @objc private func summarizeToday() {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        let day = formatter.string(from: Date())
        updateStatusIcon(symbol: "hourglass.circle.fill", tooltip: "正在整理今天的逐字稿")
        runRecorderAsync(["summary", "--date", day]) { [weak self] status, output in
            self?.refreshStatus(rebuildMenu: true)
            if status == 0 {
                self?.showAlert(title: "今日摘要完成", message: output)
            } else {
                self?.showAlert(title: "今日摘要失敗", message: output)
            }
        }
    }

    private func restartListener() -> (Int32, String) {
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        process.arguments = ["kickstart", "-k", "gui/\(getuid())/com.familyrecorder.listener"]
        process.standardOutput = output
        process.standardError = output
        do {
            try process.run()
            process.waitUntilExit()
            let text = String(
                data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8
            ) ?? ""
            return (process.terminationStatus, text.trimmingCharacters(in: .whitespacesAndNewlines))
        } catch {
            return (1, error.localizedDescription)
        }
    }

    @objc private func restartListenerFromMenu() {
        let result = restartListener()
        refreshStatus(rebuildMenu: true)
        if result.0 != 0 {
            showAlert(title: "重新啟動失敗", message: result.1)
        }
    }

    @objc private func runDoctor() {
        runRecorderAsync(["doctor"]) { [weak self] status, output in
            self?.showAlert(
                title: status == 0 ? "系統狀態正常" : "系統檢查發現問題",
                message: output
            )
        }
    }

    @objc private func refreshFromMenu() {
        refreshStatus(rebuildMenu: true)
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message.isEmpty ? "完成" : message
        alert.addButton(withTitle: "好")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    @objc private func openUninstaller() {
        guard FileManager.default.fileExists(atPath: uninstallerPath) else {
            showAlert(
                title: "找不到解除安裝器",
                message: "請使用最新版 FamilyRecorder DMG 重新安裝，或從 DMG 打開「解除安裝 FamilyRecorder」。"
            )
            return
        }
        let opened = NSWorkspace.shared.open(URL(fileURLWithPath: uninstallerPath))
        if !opened {
            showAlert(title: "無法打開解除安裝器", message: "請稍後再試，或重新啟動選單列程式。")
        }
    }

    @objc private func quitMenuBar() {
        NSApp.terminate(nil)
    }
}

func argumentValue(_ name: String) -> String? {
    guard let index = CommandLine.arguments.firstIndex(of: name) else { return nil }
    let valueIndex = CommandLine.arguments.index(after: index)
    guard valueIndex < CommandLine.arguments.endIndex else { return nil }
    return CommandLine.arguments[valueIndex]
}

func writeStandardError(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

func authorizeMicrophoneForListener() -> Bool {
    // Only the foreground menu app asks for TCC access. Background listener
    // launches merely read the decision so two simultaneous system prompts can
    // never deadlock a first install.
    AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
}

func runRecorderService(
    service: String,
    programPath: String,
    configPath: String
) -> Never {
    let recorderArguments: [String]
    switch service {
    case "listener", "listener-once":
        guard authorizeMicrophoneForListener() else {
            writeStandardError(
                "FamilyRecorder 沒有麥克風權限。請到「系統設定 → 隱私權與安全性 → 麥克風」開啟 FamilyRecorder。"
            )
            exit(77)
        }
        recorderArguments = service == "listener-once" ? ["listen", "--once"] : ["listen"]
    case "summary":
        recorderArguments = ["summary"]
    default:
        writeStandardError("Unknown FamilyRecorder service: \(service)")
        exit(64)
    }

    let process = Process()
    process.executableURL = URL(fileURLWithPath: programPath)
    process.arguments = ["--config", configPath] + recorderArguments
    var signalSources: [DispatchSourceSignal] = []
    for signalNumber in [SIGTERM, SIGINT] {
        signal(signalNumber, SIG_IGN)
        let source = DispatchSource.makeSignalSource(
            signal: signalNumber,
            queue: DispatchQueue.global(qos: .utility)
        )
        source.setEventHandler {
            if process.isRunning {
                process.terminate()
            }
        }
        source.resume()
        signalSources.append(source)
    }
    do {
        try process.run()
        process.waitUntilExit()
        signalSources.forEach { $0.cancel() }
        exit(process.terminationStatus)
    } catch {
        writeStandardError("Unable to launch FamilyRecorder \(service): \(error.localizedDescription)")
        exit(70)
    }
}

if let service = argumentValue("--service") {
    guard let serviceProgramPath = argumentValue("--program"),
          let serviceConfigPath = argumentValue("--config") else {
        writeStandardError(
            "Usage: FamilyRecorder --service listener|listener-once|summary --program PATH --config PATH"
        )
        exit(64)
    }
    runRecorderService(
        service: service,
        programPath: serviceProgramPath,
        configPath: serviceConfigPath
    )
}

guard let programPath = argumentValue("--program"),
      let configPath = argumentValue("--config"),
      let uninstallerPath = argumentValue("--uninstaller") else {
    FileHandle.standardError.write(
        Data(
            "Usage: FamilyRecorder --program PATH --config PATH --uninstaller PATH\n".utf8
        )
    )
    exit(2)
}

let application = NSApplication.shared
let delegate = AppDelegate(
    programPath: programPath,
    configPath: configPath,
    uninstallerPath: uninstallerPath
)
application.delegate = delegate
application.run()
