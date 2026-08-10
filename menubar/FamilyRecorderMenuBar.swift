import AppKit
import AVFoundation
import Darwin
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
    let speakerEnabled: Bool
    let speakerMembers: [SpeakerMember]
    let speakerProfilesDir: String

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
        case speakerEnabled = "speaker_enabled"
        case speakerMembers = "speaker_members"
        case speakerProfilesDir = "speaker_profiles_dir"
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private let programPath: String
    private let configPath: String
    private let uninstallerPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let menu = NSMenu()
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
        NSApp.setActivationPolicy(.accessory)
        menu.delegate = self
        statusItem.menu = menu
        refreshStatus(rebuildMenu: true)
        requestMicrophoneAccess { [weak self] granted in
            if !granted {
                self?.updateStatusIcon(
                    symbol: "mic.slash.circle.fill",
                    tooltip: "FamilyRecorder 需要麥克風權限"
                )
            }
        }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            self?.refreshStatus(rebuildMenu: false)
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
        summaryItem.submenu = summaryMenu
        modelMenu.addItem(summaryItem)
        modelItem.submenu = modelMenu
        menu.addItem(modelItem)

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

        menu.addItem(.separator())
        menu.addItem(item("立即整理今天", action: #selector(summarizeToday)))
        menu.addItem(item("重新啟動錄音服務", action: #selector(restartListenerFromMenu)))
        menu.addItem(item("檢查系統狀態…", action: #selector(runDoctor)))
        menu.addItem(item("重新讀取狀態", action: #selector(refreshFromMenu)))
        menu.addItem(.separator())
        menu.addItem(item("解除安裝 FamilyRecorder…", action: #selector(openUninstaller)))
        menu.addItem(item("結束選單列程式", action: #selector(quitMenuBar)))
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
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized:
        return true
    case .notDetermined:
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false
        AVCaptureDevice.requestAccess(for: .audio) { result in
            granted = result
            semaphore.signal()
        }
        guard semaphore.wait(timeout: .now() + 120) == .success else {
            writeStandardError("FamilyRecorder 等候麥克風授權逾時。")
            return false
        }
        return granted
    case .denied, .restricted:
        return false
    @unknown default:
        return false
    }
}

final class MicrophoneAuthorizationDelegate: NSObject, NSApplicationDelegate {
    private(set) var granted = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        // A regular, foreground first-run process lets macOS present the TCC
        // dialog reliably even though the normal menu-bar process is hidden.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            granted = true
            NSApp.terminate(nil)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] result in
                DispatchQueue.main.async {
                    self?.granted = result
                    NSApp.terminate(nil)
                }
            }
        case .denied, .restricted:
            NSApp.terminate(nil)
        @unknown default:
            NSApp.terminate(nil)
        }
    }
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

if CommandLine.arguments.contains("--authorize-microphone") {
    let authorizationApplication = NSApplication.shared
    let authorizationDelegate = MicrophoneAuthorizationDelegate()
    authorizationApplication.delegate = authorizationDelegate
    authorizationApplication.run()
    exit(authorizationDelegate.granted ? 0 : 77)
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
