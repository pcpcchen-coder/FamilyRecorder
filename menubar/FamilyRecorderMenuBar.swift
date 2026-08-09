import AppKit
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
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private let programPath: String
    private let configPath: String
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let menu = NSMenu()
    private var currentStatus: RecorderStatus?
    private var downloadingWhisperModel: DownloadableWhisperModel?
    private var refreshTimer: Timer?
    private var runningProcesses: [Process] = []

    init(programPath: String, configPath: String) {
        self.programPath = programPath
        self.configPath = configPath
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        menu.delegate = self
        statusItem.menu = menu
        refreshStatus(rebuildMenu: true)
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
            if let download = downloadingWhisperModel {
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

        menu.addItem(.separator())
        menu.addItem(item("立即整理今天", action: #selector(summarizeToday)))
        menu.addItem(item("重新啟動錄音服務", action: #selector(restartListenerFromMenu)))
        menu.addItem(item("檢查系統狀態…", action: #selector(runDoctor)))
        menu.addItem(item("重新讀取狀態", action: #selector(refreshFromMenu)))
        menu.addItem(.separator())
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

guard let programPath = argumentValue("--program"),
      let configPath = argumentValue("--config") else {
    FileHandle.standardError.write(
        Data("Usage: FamilyRecorderMenuBar --program PATH --config PATH\n".utf8)
    )
    exit(2)
}

let application = NSApplication.shared
let delegate = AppDelegate(programPath: programPath, configPath: configPath)
application.delegate = delegate
application.run()
