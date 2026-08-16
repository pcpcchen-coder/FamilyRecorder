import AppKit
import AVFAudio
import AVFoundation
import Darwin
import EventKit
import Foundation

struct WhisperModel: Decodable {
    let name: String
    let path: String
}

private enum MicrophonePermissionState {
    case notDetermined
    case denied
    case authorized
}

private func microphonePermissionState() -> MicrophonePermissionState {
    if #available(macOS 14.0, *) {
        switch AVAudioApplication.shared.recordPermission {
        case .undetermined:
            return .notDetermined
        case .denied:
            return .denied
        case .granted:
            return .authorized
        @unknown default:
            return .denied
        }
    }

    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .notDetermined:
        return .notDetermined
    case .denied, .restricted:
        return .denied
    case .authorized:
        return .authorized
    @unknown default:
        return .denied
    }
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

struct HallucinationFilterSettings: Decodable {
    let enabled: Bool
    let hardwareSilenceGuardEnabled: Bool
    let hardwareSilenceMaxRatio: Double
    let hardwareSilenceMaxSoftwareSpeechRatio: Double
    let hardwareSilenceMaxSNRDB: Double
    let adaptiveNoiseEnabled: Bool
    let noiseWindowChunks: Int
    let noiseMinSamples: Int
    let noiseMarginDB: Double
    let lowFrequencyFilterEnabled: Bool
    let lowFrequencyMinRatio: Double
    let tonalEnergyMinRatio: Double
    let whisperConfidenceEnabled: Bool
    let noSpeechProbabilityMax: Double
    let minAvgLogprob: Double
    let lowProbabilityThreshold: Double
    let maxLowProbabilityRatio: Double
    let maxCompressionRatio: Double
    let suppressNonSpeechTokens: Bool
    let repeatFilterEnabled: Bool
    let repeatWindowSeconds: Int
    let maxRepetitions: Int
    let repeatSimilarityThreshold: Double
    let minRepeatTextChars: Int

    enum CodingKeys: String, CodingKey {
        case enabled
        case hardwareSilenceGuardEnabled = "hardware_silence_guard_enabled"
        case hardwareSilenceMaxRatio = "hardware_silence_max_ratio"
        case hardwareSilenceMaxSoftwareSpeechRatio = "hardware_silence_max_software_speech_ratio"
        case hardwareSilenceMaxSNRDB = "hardware_silence_max_snr_db"
        case adaptiveNoiseEnabled = "adaptive_noise_enabled"
        case noiseWindowChunks = "noise_window_chunks"
        case noiseMinSamples = "noise_min_samples"
        case noiseMarginDB = "noise_margin_db"
        case lowFrequencyFilterEnabled = "low_frequency_filter_enabled"
        case lowFrequencyMinRatio = "low_frequency_min_ratio"
        case tonalEnergyMinRatio = "tonal_energy_min_ratio"
        case whisperConfidenceEnabled = "whisper_confidence_enabled"
        case noSpeechProbabilityMax = "no_speech_probability_max"
        case minAvgLogprob = "min_avg_logprob"
        case lowProbabilityThreshold = "low_probability_threshold"
        case maxLowProbabilityRatio = "max_low_probability_ratio"
        case maxCompressionRatio = "max_compression_ratio"
        case suppressNonSpeechTokens = "suppress_non_speech_tokens"
        case repeatFilterEnabled = "repeat_filter_enabled"
        case repeatWindowSeconds = "repeat_window_seconds"
        case maxRepetitions = "max_repetitions"
        case repeatSimilarityThreshold = "repeat_similarity_threshold"
        case minRepeatTextChars = "min_repeat_text_chars"
    }
}

struct HallucinationFilterStats: Decodable {
    let acoustic: Int
    let transcription: Int
    let total: Int
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

struct SmartHomeAccountStatus: Decodable {
    let id: String
    let provider: String
    let displayName: String
    let transport: String
    let status: String
    let message: String
    let requiresReauthorization: Bool
    let lastCheckedAt: String?
    let lastSuccessAt: String?
    let retryAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case provider
        case displayName = "display_name"
        case transport
        case status
        case message
        case requiresReauthorization = "requires_reauthorization"
        case lastCheckedAt = "last_checked_at"
        case lastSuccessAt = "last_success_at"
        case retryAt = "retry_at"
    }
}

struct SmartHomeCapabilityStatus: Decodable {
    let key: String
    let name: String
    let normalizedKey: String?
    let recordEnabled: Bool
    let summaryEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case key
        case name
        case normalizedKey = "normalized_key"
        case recordEnabled = "record_enabled"
        case summaryEnabled = "summary_enabled"
    }
}

struct SmartHomeDeviceStatus: Decodable {
    let selectionKey: String
    let accountID: String
    let deviceID: String
    let name: String
    let deviceType: String
    let online: Bool?
    let lastSeenAt: String
    let structureName: String
    let roomName: String
    let capabilities: [SmartHomeCapabilityStatus]

    enum CodingKeys: String, CodingKey {
        case selectionKey = "selection_key"
        case accountID = "account_id"
        case deviceID = "device_id"
        case name
        case deviceType = "device_type"
        case online
        case lastSeenAt = "last_seen_at"
        case structureName = "structure_name"
        case roomName = "room_name"
        case capabilities
    }
}

struct SmartHomeStatus: Decodable {
    let enabled: Bool
    let status: String
    let lastUpdatedAt: String
    let accounts: [SmartHomeAccountStatus]
    let devices: [SmartHomeDeviceStatus]
    let errors: [String]
    let googleNativeMacOSSupported: Bool
    let googleConnectionPath: String

    enum CodingKeys: String, CodingKey {
        case enabled
        case status
        case lastUpdatedAt = "last_updated_at"
        case accounts
        case devices
        case errors
        case googleNativeMacOSSupported = "google_native_macos_supported"
        case googleConnectionPath = "google_connection_path"
    }
}

final class SmartHomeCapabilityChoice: NSObject {
    let selectionKey: String
    let capabilityKey: String
    let scope: String
    let enabled: Bool

    init(selectionKey: String, capabilityKey: String, scope: String, enabled: Bool) {
        self.selectionKey = selectionKey
        self.capabilityKey = capabilityKey
        self.scope = scope
        self.enabled = enabled
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
    let hallucinationFilter: HallucinationFilterSettings
    let hallucinationFilterPreset: String
    let hallucinationFilterStats: HallucinationFilterStats
    let speakerEnabled: Bool
    let speakerMembers: [SpeakerMember]
    let speakerProfilesDir: String
    let directionEnabled: Bool
    let directionFrontAngleDegrees: Double
    let calendarEnabled: Bool
    let calendarAutoCreate: Bool
    let calendarProvider: String
    let calendarDefaultID: String
    let calendarDefaultName: String
    let calendarMemberIDs: [String: [String]]
    let calendarMemberDefaultIDs: [String: String]
    let calendarPendingEvents: [PendingCalendarEvent]
    let smartHome: SmartHomeStatus

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
        case hallucinationFilter = "hallucination_filter"
        case hallucinationFilterPreset = "hallucination_filter_preset"
        case hallucinationFilterStats = "hallucination_filter_stats"
        case speakerEnabled = "speaker_enabled"
        case speakerMembers = "speaker_members"
        case speakerProfilesDir = "speaker_profiles_dir"
        case directionEnabled = "direction_enabled"
        case directionFrontAngleDegrees = "direction_front_angle_degrees"
        case calendarEnabled = "calendar_enabled"
        case calendarAutoCreate = "calendar_auto_create"
        case calendarProvider = "calendar_provider"
        case calendarDefaultID = "calendar_default_id"
        case calendarDefaultName = "calendar_default_name"
        case calendarMemberIDs = "calendar_member_ids"
        case calendarMemberDefaultIDs = "calendar_member_default_ids"
        case calendarPendingEvents = "calendar_pending_events"
        case smartHome = "smart_home"
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
    private var autoCreatingCalendarEventIDs: Set<Int> = []
    private var lastCalendarAccessError: String?

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
        if microphonePermissionState() == .notDetermined {
            // Ask through the native recording-permission API immediately. A
            // menu-bar-only app is not added to System Settings' microphone
            // list until it actually makes this request.
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
            DispatchQueue.main.async { [weak self] in
                self?.handleMicrophoneAuthorizationResult()
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
            NSApp.setActivationPolicy(.accessory)
            if !granted {
                self.updateStatusIcon(
                    symbol: "mic.slash.circle.fill",
                    tooltip: "FamilyRecorder 需要麥克風權限"
                )
            } else if self.currentStatus?.listenerRunning == false {
                _ = self.restartListener()
            }
            self.restoreCalendarAccessIfNeeded()
        }
    }

    private func restoreCalendarAccessIfNeeded() {
        guard currentStatus?.calendarEnabled == true,
              EKEventStore.authorizationStatus(for: .event) == .notDetermined else {
            return
        }
        // An update can invalidate the previous TCC decision even though the
        // selected Google calendar remains configured. Ask from the normally
        // launched app so macOS attributes the permission to FamilyRecorder.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        requestCalendarAccess { [weak self] granted in
            NSApp.setActivationPolicy(.accessory)
            if !granted {
                self?.showCalendarPermissionAlert()
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
            if status.calendarAutoCreate {
                autoCreatePendingCalendarEvents(status)
            } else {
                autoCreatingCalendarEventIDs.removeAll()
            }
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
        menu.addItem(
            item(
                status.hallucinationFilter.enabled
                    ? "防幻覺：\(hallucinationPresetName(status.hallucinationFilterPreset)) · 今日攔截 \(status.hallucinationFilterStats.total) 段"
                    : "防幻覺：已關閉",
                enabled: false
            )
        )
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

        menu.addItem(buildHallucinationFilterMenu(status))

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
        menu.addItem(buildSmartHomeMenu(status))

        menu.addItem(.separator())
        menu.addItem(item("立即整理今天", action: #selector(summarizeToday)))
        menu.addItem(item("重新啟動錄音服務", action: #selector(restartListenerFromMenu)))
        menu.addItem(item("檢查系統狀態…", action: #selector(runDoctor)))
        menu.addItem(item("重新讀取狀態", action: #selector(refreshFromMenu)))
        menu.addItem(.separator())
        menu.addItem(item("解除安裝 FamilyRecorder…", action: #selector(openUninstaller)))
        menu.addItem(item("結束選單列程式", action: #selector(quitMenuBar)))
    }

    private func hallucinationPresetName(_ preset: String) -> String {
        switch preset {
        case "relaxed": return "寬鬆"
        case "balanced": return "平衡"
        case "strict": return "嚴格"
        default: return "自訂"
        }
    }

    private func buildHallucinationFilterMenu(_ status: RecorderStatus) -> NSMenuItem {
        let filterItem = item("防幻覺過濾")
        let filterMenu = NSMenu()
        filterMenu.addItem(
            item(
                status.hallucinationFilter.enabled
                    ? "已開啟 · 今日聲學攔截 \(status.hallucinationFilterStats.acoustic)／文字攔截 \(status.hallucinationFilterStats.transcription)"
                    : "目前已關閉",
                enabled: false
            )
        )
        filterMenu.addItem(
            item(
                status.hallucinationFilter.enabled ? "關閉防幻覺過濾" : "開啟防幻覺過濾",
                action: #selector(toggleHallucinationFilter)
            )
        )
        filterMenu.addItem(.separator())

        let strengthItem = item("保護強度")
        let strengthMenu = NSMenu()
        for preset in ["relaxed", "balanced", "strict"] {
            let presetItem = item(
                hallucinationPresetName(preset),
                action: #selector(selectHallucinationPreset),
                representedObject: preset
            )
            presetItem.state = status.hallucinationFilterPreset == preset ? .on : .off
            strengthMenu.addItem(presetItem)
        }
        if status.hallucinationFilterPreset == "custom" {
            let custom = item("自訂", enabled: false)
            custom.state = .on
            strengthMenu.addItem(custom)
        }
        strengthItem.submenu = strengthMenu
        filterMenu.addItem(strengthItem)
        filterMenu.addItem(
            item("進階調整門檻…", action: #selector(editHallucinationThresholds))
        )
        filterMenu.addItem(.separator())
        filterMenu.addItem(
            item("不封鎖特定句子；依聲學、信心與跨片段重複判斷", enabled: false)
        )
        filterItem.submenu = filterMenu
        return filterItem
    }

    private func buildCalendarMenu(_ status: RecorderStatus) -> NSMenuItem {
        let calendarItem = item("Google Calendar")
        let calendarMenu = NSMenu()
        let defaultName = status.calendarDefaultName.isEmpty ? "尚未選擇" : status.calendarDefaultName
        let calendarAccessIsAvailable = hasCalendarWriteAccess()
        let connectionStatus: String
        if status.calendarEnabled && !calendarAccessIsAvailable {
            connectionStatus = "需要重新授權 · 預設：\(defaultName)"
        } else if status.calendarEnabled {
            connectionStatus = "已開啟 · 預設：\(defaultName)"
        } else {
            connectionStatus = "尚未開啟 · 預設：\(defaultName)"
        }
        calendarMenu.addItem(
            item(connectionStatus, enabled: false)
        )
        calendarMenu.addItem(
            item(
                calendarAccessIsAvailable
                    ? "連接／選擇預設 Google Calendar…"
                    : "重新授權／選擇 Google Calendar…",
                action: #selector(chooseDefaultCalendar)
            )
        )
        if !status.calendarDefaultID.isEmpty {
            calendarMenu.addItem(
                item(
                    status.calendarEnabled ? "暫停產生候選事件" : "開啟候選事件",
                    action: #selector(toggleCalendarCandidates)
                )
            )
        }
        let autoCreateItem = item(
            status.calendarAutoCreate
                ? "摘要後自動加入（已開啟）"
                : "摘要後自動加入…",
            action: #selector(toggleCalendarAutoCreate),
            enabled: status.calendarEnabled && !status.calendarDefaultID.isEmpty
        )
        autoCreateItem.state = status.calendarAutoCreate ? .on : .off
        calendarMenu.addItem(autoCreateItem)

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
        calendarMenu.addItem(
            item(
                status.calendarAutoCreate
                    ? "已一次同意；摘要事件會自動寫入日曆"
                    : "目前為逐筆確認模式",
                enabled: false
            )
        )
        calendarItem.submenu = calendarMenu
        return calendarItem
    }

    private func smartHomeStatusLabel(_ status: SmartHomeStatus) -> String {
        switch status.status {
        case "disabled": return "尚未啟用"
        case "not_connected": return "尚未連接"
        case "connected": return "已連接"
        case "attention": return "需要處理"
        default: return "未連線"
        }
    }

    private func smartHomeAccountStatusLabel(_ account: SmartHomeAccountStatus) -> String {
        switch account.status {
        case "connected": return "已連線"
        case "degraded": return "連線不穩"
        case "reauthorization_required": return "需要重新授權"
        case "error": return "連線錯誤"
        default: return "未連線"
        }
    }

    private func buildSmartHomeMenu(_ recorderStatus: RecorderStatus) -> NSMenuItem {
        let status = recorderStatus.smartHome
        let homeItem = item("智慧家庭裝置")
        let homeMenu = NSMenu()
        homeMenu.addItem(item("狀態：\(smartHomeStatusLabel(status))", enabled: false))
        if !status.lastUpdatedAt.isEmpty {
            homeMenu.addItem(item("最後更新：\(status.lastUpdatedAt)", enabled: false))
        }
        for message in status.errors.prefix(3) {
            homeMenu.addItem(item("⚠️ \(message)", enabled: false))
        }

        homeMenu.addItem(.separator())
        homeMenu.addItem(
            item("連接 Google Home…", action: #selector(showGoogleHomeConnectionInfo))
        )
        homeMenu.addItem(
            item(
                "目前需由已簽章的 iPhone／iPad companion 授權",
                enabled: false
            )
        )

        if !status.accounts.isEmpty {
            homeMenu.addItem(.separator())
            for account in status.accounts {
                let accountItem = item(account.displayName)
                let accountMenu = NSMenu()
                accountMenu.addItem(
                    item("同步狀態：\(smartHomeAccountStatusLabel(account))", enabled: false)
                )
                if let lastSuccess = account.lastSuccessAt, !lastSuccess.isEmpty {
                    accountMenu.addItem(item("最後成功：\(lastSuccess)", enabled: false))
                }
                if !account.message.isEmpty {
                    accountMenu.addItem(item(account.message, enabled: false))
                }
                if account.requiresReauthorization {
                    accountMenu.addItem(
                        item("重新授權…", action: #selector(showGoogleHomeConnectionInfo))
                    )
                }
                accountMenu.addItem(.separator())
                accountMenu.addItem(
                    item(
                        "移除此連線…",
                        action: #selector(disconnectSmartHomeAccount),
                        representedObject: account.id
                    )
                )
                accountItem.submenu = accountMenu
                homeMenu.addItem(accountItem)
            }
        }

        homeMenu.addItem(.separator())
        let selectionItem = item("選擇住家／房間／裝置屬性")
        let selectionMenu = NSMenu()
        if status.devices.isEmpty {
            selectionMenu.addItem(item("尚未探索到裝置", enabled: false))
        } else {
            let accountNames = Dictionary(
                uniqueKeysWithValues: status.accounts.map { ($0.id, $0.displayName) }
            )
            let accountDevices = Dictionary(grouping: status.devices) { $0.accountID }
            let accountIDs = accountDevices.keys.sorted {
                (accountNames[$0] ?? $0) < (accountNames[$1] ?? $1)
            }
            for accountID in accountIDs {
                let accountItem = item(accountNames[accountID] ?? accountID)
                let accountMenu = NSMenu()
                let structures = Dictionary(
                    grouping: accountDevices[accountID] ?? []
                ) { $0.structureName }
                for structureName in structures.keys.sorted() {
                    let structureItem = item(structureName)
                    let structureMenu = NSMenu()
                    let rooms = Dictionary(
                        grouping: structures[structureName] ?? []
                    ) { $0.roomName }
                    for roomName in rooms.keys.sorted() {
                        let roomItem = item(roomName)
                        let roomMenu = NSMenu()
                        for device in (rooms[roomName] ?? []).sorted(by: { $0.name < $1.name }) {
                            let onlineLabel = device.online == false ? "（離線）" : ""
                            let deviceItem = item("\(device.name)\(onlineLabel)")
                            let deviceMenu = NSMenu()
                            for capability in device.capabilities {
                                let capabilityItem = item(capability.name)
                                let capabilityMenu = NSMenu()
                                let recordChoice = SmartHomeCapabilityChoice(
                                    selectionKey: device.selectionKey,
                                    capabilityKey: capability.key,
                                    scope: "record",
                                    enabled: !capability.recordEnabled
                                )
                                let recordItem = item(
                                    "記錄原始狀態（僅本機）",
                                    action: #selector(toggleSmartHomeCapability),
                                    representedObject: recordChoice
                                )
                                recordItem.state = capability.recordEnabled ? .on : .off
                                capabilityMenu.addItem(recordItem)
                                let summaryChoice = SmartHomeCapabilityChoice(
                                    selectionKey: device.selectionKey,
                                    capabilityKey: capability.key,
                                    scope: "summary",
                                    enabled: !capability.summaryEnabled
                                )
                                let summaryItem = item(
                                    "允許文字事件進每日摘要",
                                    action: #selector(toggleSmartHomeCapability),
                                    representedObject: summaryChoice
                                )
                                summaryItem.state = capability.summaryEnabled ? .on : .off
                                capabilityMenu.addItem(summaryItem)
                                if capability.normalizedKey == nil {
                                    capabilityMenu.addItem(
                                        item(
                                            "未知屬性會原樣保存在本機，不自動進摘要",
                                            enabled: false
                                        )
                                    )
                                }
                                capabilityItem.submenu = capabilityMenu
                                deviceMenu.addItem(capabilityItem)
                            }
                            deviceItem.submenu = deviceMenu
                            roomMenu.addItem(deviceItem)
                        }
                        roomItem.submenu = roomMenu
                        structureMenu.addItem(roomItem)
                    }
                    structureItem.submenu = structureMenu
                    accountMenu.addItem(structureItem)
                }
                accountItem.submenu = accountMenu
                selectionMenu.addItem(accountItem)
            }
        }
        selectionItem.submenu = selectionMenu
        homeMenu.addItem(selectionItem)
        homeMenu.addItem(.separator())
        homeMenu.addItem(
            item("重新讀取本機同步狀態", action: #selector(refreshFromMenu))
        )
        homeMenu.addItem(
            item("本階段唯讀記錄，不提供遠端開關或控制", enabled: false)
        )
        homeItem.submenu = homeMenu
        return homeItem
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

    @objc private func showGoogleHomeConnectionInfo() {
        let alert = NSAlert()
        alert.messageText = "Google Home 需要行動裝置 companion"
        alert.informativeText = """
        Google 官方 Home APIs SDK 目前只支援 Android 與 iOS，不能由這個原生 macOS App 直接登入。FamilyRecorder 已建立安全的 companion bridge 邊界，但尚未建立或連接任何 Google Cloud 專案。

        下一階段需由你決定是否建立 Google Cloud OAuth 設定，並用已簽章的 iPhone／iPad companion 完成 Google 授權；Mac 只接收不含憑證的狀態事件。
        """
        alert.addButton(withTitle: "好")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    @objc private func toggleSmartHomeCapability(_ sender: NSMenuItem) {
        guard let choice = sender.representedObject as? SmartHomeCapabilityChoice else { return }
        runSimpleAction(
            [
                "set-home-capability",
                "--scope", choice.scope,
                "--selection-key", choice.selectionKey,
                "--capability", choice.capabilityKey,
                "--enabled", choice.enabled ? "true" : "false"
            ],
            successTitle: ""
        )
    }

    @objc private func disconnectSmartHomeAccount(_ sender: NSMenuItem) {
        guard let accountID = sender.representedObject as? String else { return }
        let alert = NSAlert()
        alert.messageText = "移除智慧家庭連線？"
        alert.informativeText = "這會停止後續同步並清除該連線的 allowlist；既有本機事件會保留。"
        alert.addButton(withTitle: "移除連線")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runSimpleAction(
            ["disconnect-home-account", "--account-id", accountID],
            successTitle: "智慧家庭連線已移除"
        )
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
        lastCalendarAccessError = nil
        let finished: (Bool, Error?) -> Void = { [weak self] granted, error in
            DispatchQueue.main.async {
                self?.lastCalendarAccessError = error?.localizedDescription
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
        if let error = lastCalendarAccessError, !error.isEmpty {
            alert.informativeText =
                "macOS 拒絕了行事曆授權請求：\n\n\(error)\n\n請確認安裝的是最新版 FamilyRecorder，再到「系統設定 → 隱私權與安全性 → 行事曆」檢查。"
        } else {
            alert.informativeText =
                "請在「系統設定 → 隱私權與安全性 → 行事曆」允許 FamilyRecorder，才能列出日曆並建立事件。"
        }
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

    @objc private func toggleCalendarAutoCreate() {
        guard let status = currentStatus else { return }
        if status.calendarAutoCreate {
            runSimpleAction(
                ["set-calendar-auto-create", "--enabled", "false"],
                successTitle: "已恢復逐筆確認模式"
            )
            return
        }
        requestCalendarAccess { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.showCalendarPermissionAlert()
                return
            }
            guard !self.availableGoogleCalendars.isEmpty else {
                self.showMissingGoogleCalendarAlert()
                return
            }
            let pendingCount = status.calendarPendingEvents.count
            let pendingText = pendingCount == 0
                ? "目前沒有待確認事件。"
                : "目前已有 \(pendingCount) 個待確認事件；開啟後也會立即自動加入。"
            let alert = NSAlert()
            alert.messageText = "摘要後自動加入 Google Calendar？"
            alert.informativeText =
                "這是一次性同意。今後 ChatGPT 從摘要擷取的事件，會自動寫入成員或全家預設日曆，不再逐筆詢問。\n\n\(pendingText)\n\n語音辨識與 AI 判斷仍可能出錯；你可以隨時回到這裡關閉。"
            alert.addButton(withTitle: "同意並開啟")
            alert.addButton(withTitle: "取消")
            NSApp.activate(ignoringOtherApps: true)
            guard alert.runModal() == .alertFirstButtonReturn else { return }
            self.runSimpleAction(
                ["set-calendar-auto-create", "--enabled", "true"],
                successTitle: ""
            )
        }
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

    private func hasCalendarWriteAccess() -> Bool {
        let status = EKEventStore.authorizationStatus(for: .event)
        if #available(macOS 14.0, *) {
            return status == .fullAccess
        } else {
            return status == .authorized
        }
    }

    private func calendarCandidateMarker(_ candidate: PendingCalendarEvent) -> String {
        "FamilyRecorder candidate \(candidate.summaryDate)#\(candidate.id)|\(candidate.startsAt)|\(candidate.title)"
    }

    private func existingCalendarEventID(
        for candidate: PendingCalendarEvent,
        startDate: Date,
        endDate: Date
    ) -> String? {
        let marker = calendarCandidateMarker(candidate)
        let margin: TimeInterval = 86_400
        let predicate = eventStore.predicateForEvents(
            withStart: startDate.addingTimeInterval(-margin),
            end: endDate.addingTimeInterval(margin),
            calendars: nil
        )
        return eventStore.events(matching: predicate).first {
            $0.notes?.contains(marker) == true
        }?.eventIdentifier
    }

    private func autoCreatePendingCalendarEvents(_ status: RecorderStatus) {
        guard status.calendarEnabled, status.calendarAutoCreate, hasCalendarWriteAccess() else {
            return
        }
        if availableGoogleCalendars.isEmpty {
            refreshGoogleCalendars()
        }
        for candidate in status.calendarPendingEvents
        where !autoCreatingCalendarEventIDs.contains(candidate.id) {
            guard let calendar = suggestedCalendar(for: candidate) else { continue }
            autoCreatingCalendarEventIDs.insert(candidate.id)
            createCalendarEvent(candidate, in: calendar, requiresConfirmation: false)
        }
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
            self.createCalendarEvent(event, in: calendar, requiresConfirmation: true)
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
            self.createCalendarEvent(event, in: calendar, requiresConfirmation: true)
        }
    }

    private func createCalendarEvent(
        _ candidate: PendingCalendarEvent,
        in calendar: EKCalendar,
        requiresConfirmation: Bool
    ) {
        guard let (startDate, endDate) = dates(for: candidate) else {
            showAlert(
                title: requiresConfirmation ? "事件時間格式錯誤" : "自動加入行事曆失敗",
                message: "「\(candidate.title)」的時間格式不正確，已保留在待確認事件。"
            )
            return
        }
        if requiresConfirmation {
            let alert = NSAlert()
            alert.messageText = "加入 Google Calendar？"
            let member = candidate.memberName.isEmpty ? "未指定" : candidate.memberName
            alert.informativeText =
                "事件：\(candidate.title)\n時間：\(calendarEventTime(candidate))\n成員：\(member)\n日曆：\(calendarDisplayName(calendar))\n\n只有按下確認後才會真正建立。"
            alert.addButton(withTitle: "確認建立")
            alert.addButton(withTitle: "取消")
            NSApp.activate(ignoringOtherApps: true)
            guard alert.runModal() == .alertFirstButtonReturn else { return }
        }
        if let existingID = existingCalendarEventID(
            for: candidate, startDate: startDate, endDate: endDate
        ) {
            markCalendarCandidateCreated(
                candidate,
                externalID: existingID,
                calendar: calendar,
                automatic: !requiresConfirmation
            )
            return
        }

        let event = EKEvent(eventStore: eventStore)
        event.calendar = calendar
        event.title = candidate.title
        event.startDate = startDate
        event.endDate = endDate
        event.isAllDay = candidate.allDay
        let sourceNote = requiresConfirmation
            ? "由 FamilyRecorder 每日摘要產生，並經使用者確認。"
            : "由 FamilyRecorder 每日摘要自動建立；使用者已事先開啟自動加入。"
        let marker = calendarCandidateMarker(candidate)
        let provenance = "\(sourceNote)\n\(marker)"
        event.notes = candidate.notes.isEmpty
            ? provenance
            : "\(provenance)\n\(candidate.notes)"
        do {
            try eventStore.save(event, span: .thisEvent, commit: true)
        } catch {
            showAlert(
                title: requiresConfirmation ? "無法建立行事曆事件" : "自動加入行事曆失敗",
                message: "「\(candidate.title)」：\(error.localizedDescription)\n事件仍保留在待確認清單。"
            )
            return
        }
        markCalendarCandidateCreated(
            candidate,
            externalID: event.eventIdentifier ?? "",
            calendar: calendar,
            automatic: !requiresConfirmation
        )
    }

    private func markCalendarCandidateCreated(
        _ candidate: PendingCalendarEvent,
        externalID: String,
        calendar: EKCalendar,
        automatic: Bool
    ) {
        runRecorderAsync(
            [
                "calendar-event-created",
                "--id", String(candidate.id),
                "--external-id", externalID,
            ]
        ) { [weak self] status, output in
            guard let self else { return }
            if status == 0 {
                self.autoCreatingCalendarEventIDs.remove(candidate.id)
            }
            self.refreshStatus(rebuildMenu: true)
            if !automatic || status != 0 {
                self.showAlert(
                    title: status == 0 ? "已加入 Google Calendar" : "事件已建立，但狀態更新失敗",
                    message: status == 0 ? self.calendarDisplayName(calendar) : output
                )
            }
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

    private func restartAfterHallucinationSetting(
        status: Int32,
        output: String,
        successTitle: String
    ) {
        guard status == 0 else {
            showAlert(title: "防幻覺設定失敗", message: output)
            return
        }
        let restart = restartListener()
        refreshStatus(rebuildMenu: true)
        showAlert(
            title: restart.0 == 0 ? successTitle : "設定已儲存，但錄音服務重啟失敗",
            message: restart.0 == 0 ? output : "\(output)\n\(restart.1)"
        )
    }

    @objc private func toggleHallucinationFilter() {
        let enabled = !(currentStatus?.hallucinationFilter.enabled ?? true)
        runRecorderAsync(
            ["set-hallucination-filter", "--enabled", enabled ? "true" : "false"]
        ) { [weak self] status, output in
            self?.restartAfterHallucinationSetting(
                status: status,
                output: output,
                successTitle: enabled ? "防幻覺過濾已開啟" : "防幻覺過濾已關閉"
            )
        }
    }

    @objc private func selectHallucinationPreset(_ sender: NSMenuItem) {
        guard let preset = sender.representedObject as? String else { return }
        let alert = NSAlert()
        alert.messageText = "切換為「\(hallucinationPresetName(preset))」保護？"
        alert.informativeText =
            preset == "strict"
                ? "嚴格模式會攔截更多低信心與疑似底噪內容，也可能略過很短或很輕聲的真實說話。"
                : "這會更新所有防幻覺門檻；之後仍可進階微調。"
        alert.addButton(withTitle: "切換")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runRecorderAsync(["set-hallucination-preset", "--name", preset]) { [weak self] status, output in
            self?.restartAfterHallucinationSetting(
                status: status,
                output: output,
                successTitle: "防幻覺保護已切換"
            )
        }
    }

    private func thresholdField(_ value: Double, decimals: Int = 1) -> NSTextField {
        let field = NSTextField(string: String(format: "%.*f", decimals, value))
        field.alignment = .right
        field.font = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        field.widthAnchor.constraint(equalToConstant: 76).isActive = true
        return field
    }

    @objc private func editHallucinationThresholds() {
        guard let settings = currentStatus?.hallucinationFilter else { return }
        let alert = NSAlert()
        alert.messageText = "進階調整防幻覺門檻"
        alert.informativeText =
            "百分比越高不一定越嚴格；每列說明的是允許或拒絕的界線。不確定時建議使用「平衡」。"

        let enabled = NSButton(checkboxWithTitle: "啟用整體防幻覺過濾", target: nil, action: nil)
        enabled.state = settings.enabled ? .on : .off
        let hardware = NSButton(checkboxWithTitle: "採用 XVF3800 硬體靜音證據", target: nil, action: nil)
        hardware.state = settings.hardwareSilenceGuardEnabled ? .on : .off
        let adaptive = NSButton(checkboxWithTitle: "採用自適應背景噪音基線", target: nil, action: nil)
        adaptive.state = settings.adaptiveNoiseEnabled ? .on : .off
        let lowFrequency = NSButton(checkboxWithTitle: "偵測低頻固定音／電氣底噪", target: nil, action: nil)
        lowFrequency.state = settings.lowFrequencyFilterEnabled ? .on : .off
        let confidence = NSButton(checkboxWithTitle: "檢查 Whisper 信心", target: nil, action: nil)
        confidence.state = settings.whisperConfidenceEnabled ? .on : .off
        let suppressNonSpeech = NSButton(checkboxWithTitle: "抑制 Whisper 非語音 token", target: nil, action: nil)
        suppressNonSpeech.state = settings.suppressNonSpeechTokens ? .on : .off
        let repeatFilter = NSButton(checkboxWithTitle: "攔截跨片段重複長句", target: nil, action: nil)
        repeatFilter.state = settings.repeatFilterEnabled ? .on : .off

        let hardwareRatio = thresholdField(settings.hardwareSilenceMaxRatio * 100)
        let softwareRatio = thresholdField(settings.hardwareSilenceMaxSoftwareSpeechRatio * 100)
        let snr = thresholdField(settings.hardwareSilenceMaxSNRDB)
        let noiseWindow = thresholdField(Double(settings.noiseWindowChunks), decimals: 0)
        let noiseSamples = thresholdField(Double(settings.noiseMinSamples), decimals: 0)
        let noiseMargin = thresholdField(settings.noiseMarginDB)
        let lowRatio = thresholdField(settings.lowFrequencyMinRatio * 100)
        let tonalRatio = thresholdField(settings.tonalEnergyMinRatio * 100)
        let noSpeech = thresholdField(settings.noSpeechProbabilityMax * 100)
        let avgLogprob = thresholdField(settings.minAvgLogprob, decimals: 2)
        let lowTokenProbability = thresholdField(settings.lowProbabilityThreshold * 100)
        let lowTokenRatio = thresholdField(settings.maxLowProbabilityRatio * 100)
        let compression = thresholdField(settings.maxCompressionRatio, decimals: 2)
        let repeatMinutes = thresholdField(Double(settings.repeatWindowSeconds) / 60)
        let repetitions = thresholdField(Double(settings.maxRepetitions), decimals: 0)
        let repeatSimilarity = thresholdField(settings.repeatSimilarityThreshold * 100)
        let repeatCharacters = thresholdField(Double(settings.minRepeatTextChars), decimals: 0)

        let rows: [[NSView]] = [
            [NSTextField(labelWithString: "硬體靜音上限"), hardwareRatio, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "硬體靜音時軟體語音上限"), softwareRatio, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "弱訊號 SNR 上限"), snr, NSTextField(labelWithString: "dB")],
            [NSTextField(labelWithString: "背景基線歷史長度"), noiseWindow, NSTextField(labelWithString: "chunks")],
            [NSTextField(labelWithString: "背景基線最少樣本"), noiseSamples, NSTextField(labelWithString: "chunks")],
            [NSTextField(labelWithString: "背景基線容許範圍"), noiseMargin, NSTextField(labelWithString: "dB")],
            [NSTextField(labelWithString: "低頻能量下限"), lowRatio, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "固定窄頻能量下限"), tonalRatio, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "Whisper 無語音機率上限"), noSpeech, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "Whisper 平均 log probability 下限"), avgLogprob, NSTextField(labelWithString: "-5～0")],
            [NSTextField(labelWithString: "低可信 token 界線"), lowTokenProbability, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "低可信 token 比例上限"), lowTokenRatio, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "文字壓縮／重複率上限"), compression, NSTextField(labelWithString: "ratio")],
            [NSTextField(labelWithString: "跨片段比對時間"), repeatMinutes, NSTextField(labelWithString: "分鐘")],
            [NSTextField(labelWithString: "同句允許出現次數"), repetitions, NSTextField(labelWithString: "次")],
            [NSTextField(labelWithString: "重複句相似度下限"), repeatSimilarity, NSTextField(labelWithString: "%")],
            [NSTextField(labelWithString: "重複檢查最短文字"), repeatCharacters, NSTextField(labelWithString: "字")],
        ]
        let grid = NSGridView(views: rows)
        grid.rowSpacing = 5
        grid.columnSpacing = 8
        grid.xPlacement = .leading

        let stack = NSStackView(views: [
            enabled, hardware, adaptive, lowFrequency, confidence, suppressNonSpeech,
            repeatFilter, grid,
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 5
        stack.edgeInsets = NSEdgeInsets(top: 4, left: 4, bottom: 4, right: 4)
        stack.frame = NSRect(x: 0, y: 0, width: 560, height: 570)
        alert.accessoryView = stack
        alert.addButton(withTitle: "儲存並重啟")
        alert.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        let arguments = [
            "set-hallucination-filter",
            "--enabled", enabled.state == .on ? "true" : "false",
            "--hardware-silence-guard-enabled", hardware.state == .on ? "true" : "false",
            "--adaptive-noise-enabled", adaptive.state == .on ? "true" : "false",
            "--low-frequency-filter-enabled", lowFrequency.state == .on ? "true" : "false",
            "--whisper-confidence-enabled", confidence.state == .on ? "true" : "false",
            "--suppress-non-speech-tokens", suppressNonSpeech.state == .on ? "true" : "false",
            "--repeat-filter-enabled", repeatFilter.state == .on ? "true" : "false",
            "--hardware-silence-max-ratio", String(hardwareRatio.doubleValue / 100),
            "--hardware-silence-max-software-speech-ratio", String(softwareRatio.doubleValue / 100),
            "--hardware-silence-max-snr-db", String(snr.doubleValue),
            "--noise-window-chunks", String(Int(noiseWindow.doubleValue.rounded())),
            "--noise-min-samples", String(Int(noiseSamples.doubleValue.rounded())),
            "--noise-margin-db", String(noiseMargin.doubleValue),
            "--low-frequency-min-ratio", String(lowRatio.doubleValue / 100),
            "--tonal-energy-min-ratio", String(tonalRatio.doubleValue / 100),
            "--no-speech-probability-max", String(noSpeech.doubleValue / 100),
            "--min-avg-logprob", String(avgLogprob.doubleValue),
            "--low-probability-threshold", String(lowTokenProbability.doubleValue / 100),
            "--max-low-probability-ratio", String(lowTokenRatio.doubleValue / 100),
            "--max-compression-ratio", String(compression.doubleValue),
            "--repeat-window-seconds", String(Int((repeatMinutes.doubleValue * 60).rounded())),
            "--max-repetitions", String(Int(repetitions.doubleValue.rounded())),
            "--repeat-similarity-threshold", String(repeatSimilarity.doubleValue / 100),
            "--min-repeat-text-chars", String(Int(repeatCharacters.doubleValue.rounded())),
        ]
        runRecorderAsync(arguments) { [weak self] status, output in
            self?.restartAfterHallucinationSetting(
                status: status,
                output: output,
                successTitle: "防幻覺門檻已更新"
            )
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
        if #available(macOS 14.0, *) {
            switch AVAudioApplication.shared.recordPermission {
            case .granted:
                registerNativeMicrophoneUse(completion: completion)
            case .undetermined:
                AVAudioApplication.requestRecordPermission { granted in
                    guard granted else {
                        DispatchQueue.main.async { completion(false) }
                        return
                    }
                    self.registerNativeMicrophoneUse(completion: completion)
                }
            case .denied:
                completion(false)
            @unknown default:
                completion(false)
            }
            return
        }

        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            registerNativeMicrophoneUse(completion: completion)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                guard granted else {
                    DispatchQueue.main.async { completion(false) }
                    return
                }
                self.registerNativeMicrophoneUse(completion: completion)
            }
        case .denied, .restricted:
            completion(false)
        @unknown default:
            completion(false)
        }
    }

    private func registerNativeMicrophoneUse(completion: @escaping (Bool) -> Void) {
        // The long-running recorder is a Python child process. Exercise the
        // audio device once in the signed native app after first authorization
        // so macOS TCC records FamilyRecorder itself as the microphone client
        // and keeps it visible in System Settings.
        guard let device = AVCaptureDevice.default(for: .audio),
              let input = try? AVCaptureDeviceInput(device: device) else {
            DispatchQueue.main.async { completion(true) }
            return
        }
        let session = AVCaptureSession()
        let output = AVCaptureAudioDataOutput()
        session.beginConfiguration()
        if session.canAddInput(input) {
            session.addInput(input)
        }
        if session.canAddOutput(output) {
            session.addOutput(output)
        }
        session.commitConfiguration()
        DispatchQueue.global(qos: .userInitiated).async {
            session.startRunning()
            Thread.sleep(forTimeInterval: 0.5)
            session.stopRunning()
            DispatchQueue.main.async { completion(true) }
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
    microphonePermissionState() == .authorized
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

let homeDirectory = FileManager.default.homeDirectoryForCurrentUser
let runtimeDirectory = homeDirectory
    .appendingPathComponent("Library/Application Support/FamilyRecorder", isDirectory: true)
let programPath = argumentValue("--program")
    ?? runtimeDirectory.appendingPathComponent("venv/bin/family-recorder").path
let configPath = argumentValue("--config")
    ?? homeDirectory.appendingPathComponent(".config/familyrecorder/config.yaml").path
let uninstallerPath = argumentValue("--uninstaller")
    ?? runtimeDirectory.appendingPathComponent("解除安裝 FamilyRecorder.app").path

// The installer first opens the standard /Applications bundle through Launch
// Services so macOS attributes the native microphone request to FamilyRecorder
// itself. The LaunchAgent is registered immediately afterwards; if that second
// GUI instance starts in the same session, exit successfully and leave the
// foreground instance in charge. Background --service processes are handled
// above and never take this branch.
let currentProcessIdentifier = ProcessInfo.processInfo.processIdentifier
let anotherMenuInstanceIsRunning = NSRunningApplication.runningApplications(
    withBundleIdentifier: "com.familyrecorder.app"
).contains { application in
    application.processIdentifier != currentProcessIdentifier
        && application.activationPolicy != .prohibited
}
if anotherMenuInstanceIsRunning {
    exit(0)
}

let application = NSApplication.shared
let delegate = AppDelegate(
    programPath: programPath,
    configPath: configPath,
    uninstallerPath: uninstallerPath
)
application.delegate = delegate
application.run()
