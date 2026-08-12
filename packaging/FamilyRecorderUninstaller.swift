import AppKit
import Foundation

private enum RemovalMode: String {
    case keepData = "keep-data"
    case all
}

private final class UninstallerDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private let installedStatus = NSTextField(wrappingLabelWithString: "正在檢查安裝內容…")
    private let runtimeStatus = NSTextField(wrappingLabelWithString: "")
    private let dataStatus = NSTextField(wrappingLabelWithString: "")
    private let configStatus = NSTextField(wrappingLabelWithString: "")
    private let keepDataButton = NSButton(
        radioButtonWithTitle: "只移除程式，保留家庭資料與設定",
        target: nil,
        action: nil
    )
    private let removeAllButton = NSButton(
        radioButtonWithTitle: "完整移除，包括所有模型、錄音與紀錄",
        target: nil,
        action: nil
    )
    private let progress = NSProgressIndicator()
    private let uninstallButton = NSButton(title: "解除安裝…", target: nil, action: nil)
    private var inspection: [String: String] = [:]
    private var activeProcess: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildWindow()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        inspectInstallation()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 640, height: 540),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.title = "解除安裝 FamilyRecorder"
        window.isReleasedWhenClosed = false

        let title = NSTextField(labelWithString: "解除安裝 FamilyRecorder")
        title.font = .systemFont(ofSize: 26, weight: .bold)

        let explanation = NSTextField(
            wrappingLabelWithString:
                "解除安裝器會先停止錄音、每日摘要與選單列服務，再把選定內容移到垃圾桶。ChatGPT／Codex 登入與共用 Homebrew 工具不會受到影響。"
        )
        explanation.textColor = .secondaryLabelColor

        let contentBox = NSBox()
        contentBox.title = "這台 Mac 上的 FamilyRecorder"
        contentBox.contentView = installationContent()

        keepDataButton.state = .on
        removeAllButton.state = .off
        keepDataButton.target = self
        keepDataButton.action = #selector(selectKeepData)
        removeAllButton.target = self
        removeAllButton.action = #selector(selectRemoveAll)

        let choiceTitle = NSTextField(labelWithString: "選擇移除方式")
        choiceTitle.font = .systemFont(ofSize: 13, weight: .semibold)
        let keepDetail = NSTextField(
            wrappingLabelWithString:
                "保留逐字稿、摘要、錄音、SQLite、人聲樣本與設定，之後重新安裝可繼續使用。"
        )
        keepDetail.textColor = .secondaryLabelColor
        keepDetail.font = .systemFont(ofSize: 12)
        let allDetail = NSTextField(
            wrappingLabelWithString:
                "移除程式、所有 Whisper 模型、錄音、逐字稿、摘要、資料庫、人聲樣本、測試結果、Log 與設定。"
        )
        allDetail.textColor = .secondaryLabelColor
        allDetail.font = .systemFont(ofSize: 12)

        let choiceStack = NSStackView(views: [
            choiceTitle, keepDataButton, keepDetail, removeAllButton, allDetail,
        ])
        choiceStack.orientation = .vertical
        choiceStack.alignment = .leading
        choiceStack.spacing = 7

        progress.style = .spinning
        progress.controlSize = .small
        progress.isDisplayedWhenStopped = false
        uninstallButton.target = self
        uninstallButton.action = #selector(beginUninstall)
        uninstallButton.bezelStyle = .rounded
        uninstallButton.keyEquivalent = "\r"
        uninstallButton.isEnabled = false

        let actionRow = NSStackView(views: [progress, uninstallButton])
        actionRow.orientation = .horizontal
        actionRow.alignment = .centerY
        actionRow.spacing = 10
        actionRow.distribution = .gravityAreas

        let safety = NSTextField(
            wrappingLabelWithString:
                "為避免誤刪，所有內容會先放進垃圾桶；確認不需復原後再由你清空垃圾桶。"
        )
        safety.font = .systemFont(ofSize: 11)
        safety.textColor = .tertiaryLabelColor

        let stack = NSStackView(views: [
            title, explanation, contentBox, choiceStack, actionRow, safety,
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        guard let content = window.contentView else { return }
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 24),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: content.bottomAnchor, constant: -22),
            explanation.widthAnchor.constraint(equalTo: stack.widthAnchor),
            contentBox.widthAnchor.constraint(equalTo: stack.widthAnchor),
            choiceStack.widthAnchor.constraint(equalTo: stack.widthAnchor),
            keepDetail.widthAnchor.constraint(equalTo: choiceStack.widthAnchor),
            allDetail.widthAnchor.constraint(equalTo: choiceStack.widthAnchor),
            actionRow.widthAnchor.constraint(equalTo: stack.widthAnchor),
            safety.widthAnchor.constraint(equalTo: stack.widthAnchor),
        ])
    }

    private func installationContent() -> NSView {
        installedStatus.font = .systemFont(ofSize: 13, weight: .semibold)
        for label in [runtimeStatus, dataStatus, configStatus] {
            label.font = .systemFont(ofSize: 12)
            label.textColor = .secondaryLabelColor
        }
        let stack = NSStackView(views: [
            installedStatus, runtimeStatus, dataStatus, configStatus,
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 6
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = NSView()
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 10),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
        ])
        return content
    }

    private func helperPath() -> String? {
        Bundle.main.url(forResource: "uninstall_family_recorder", withExtension: "sh")?.path
    }

    private func parseValues(_ output: String) -> [String: String] {
        var values: [String: String] = [:]
        for line in output.split(separator: "\n", omittingEmptySubsequences: true) {
            let parts = line.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            if parts.count == 2 {
                values[String(parts[0])] = String(parts[1])
            }
        }
        return values
    }

    private func formattedBytes(_ value: String?) -> String {
        guard let value, let bytes = Int64(value) else { return "0 KB" }
        return ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
    }

    private func runHelper(
        _ arguments: [String],
        completion: @escaping (Int32, String) -> Void
    ) {
        guard activeProcess == nil else { return }
        guard let helper = helperPath() else {
            showAlert(title: "解除安裝器不完整", message: "找不到解除安裝所需的安全清理程式。")
            return
        }
        setBusy(true)
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [helper] + arguments
        process.standardOutput = output
        process.standardError = output
        activeProcess = process
        process.terminationHandler = { [weak self] finished in
            let text = String(
                data: output.fileHandleForReading.readDataToEndOfFile(),
                encoding: .utf8
            ) ?? ""
            DispatchQueue.main.async {
                self?.activeProcess = nil
                self?.setBusy(false)
                completion(finished.terminationStatus, text)
            }
        }
        do {
            try process.run()
        } catch {
            activeProcess = nil
            setBusy(false)
            completion(1, error.localizedDescription)
        }
    }

    private func setBusy(_ busy: Bool) {
        if busy {
            progress.startAnimation(nil)
        } else {
            progress.stopAnimation(nil)
        }
        keepDataButton.isEnabled = !busy
        removeAllButton.isEnabled = !busy
        uninstallButton.isEnabled = !busy && inspection["INSTALLED"] == "1"
    }

    private func inspectInstallation() {
        runHelper(["inspect"]) { [weak self] status, output in
            guard let self else { return }
            guard status == 0 else {
                self.installedStatus.stringValue = "無法檢查 FamilyRecorder 安裝內容"
                self.installedStatus.textColor = .systemRed
                self.showAlert(title: "檢查失敗", message: output)
                return
            }
            self.inspection = self.parseValues(output)
            guard self.inspection["INSTALLED"] == "1" else {
                self.installedStatus.stringValue = "這台 Mac 沒有找到 FamilyRecorder 安裝內容"
                self.installedStatus.textColor = .secondaryLabelColor
                self.runtimeStatus.stringValue = ""
                self.dataStatus.stringValue = ""
                self.configStatus.stringValue = ""
                self.uninstallButton.isEnabled = false
                return
            }
            let totalSize = self.formattedBytes(self.inspection["TOTAL_BYTES"])
            let programSize = self.formattedBytes(self.inspection["PROGRAM_BYTES"])
            let dataSize = self.formattedBytes(self.inspection["DATA_BYTES"])
            let configSize = self.formattedBytes(self.inspection["CONFIG_BYTES"])
            self.installedStatus.stringValue = "總計約 \(totalSize)"
            self.installedStatus.textColor = .labelColor
            self.runtimeStatus.stringValue = "App、程式元件與 Whisper 模型：\(programSize)"
            self.dataStatus.stringValue = "家庭錄音與紀錄：\(dataSize)"
            self.configStatus.stringValue = "設定：\(configSize)"
            self.uninstallButton.isEnabled = true
        }
    }

    @objc private func selectKeepData() {
        keepDataButton.state = .on
        removeAllButton.state = .off
    }

    @objc private func selectRemoveAll() {
        keepDataButton.state = .off
        removeAllButton.state = .on
    }

    @objc private func beginUninstall() {
        let mode: RemovalMode = removeAllButton.state == .on ? .all : .keepData
        let confirmation = NSAlert()
        confirmation.alertStyle = mode == .all ? .critical : .warning
        confirmation.messageText = mode == .all
            ? "完整移除 FamilyRecorder？"
            : "移除 FamilyRecorder 程式？"
        confirmation.informativeText = mode == .all
            ? "將停止所有背景服務，並把程式、Whisper 模型、所有錄音、逐字稿、摘要、資料庫、人聲樣本及設定移到垃圾桶。"
            : "將停止所有背景服務並把程式與 Whisper 模型移到垃圾桶；家庭資料與設定會保留。"
        confirmation.addButton(withTitle: mode == .all ? "完整移除" : "移除程式")
        confirmation.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard confirmation.runModal() == .alertFirstButtonReturn else { return }

        runHelper(["uninstall", mode.rawValue]) { [weak self] status, output in
            guard let self else { return }
            guard status == 0 else {
                self.showAlert(title: "解除安裝未完成", message: output)
                return
            }
            let result = self.parseValues(output)
            let trashPath = result["TRASH_PATH"] ?? "垃圾桶"
            let alert = NSAlert()
            alert.messageText = "FamilyRecorder 已解除安裝"
            alert.informativeText = mode == .all
                ? "程式、模型與所有家庭資料已移到垃圾桶。確認不需復原後，可清空垃圾桶。"
                : "程式與模型已移到垃圾桶；家庭資料與設定仍保留在原本位置。"
            alert.addButton(withTitle: "打開垃圾桶內容")
            alert.addButton(withTitle: "完成")
            NSApp.activate(ignoringOtherApps: true)
            if alert.runModal() == .alertFirstButtonReturn {
                NSWorkspace.shared.open(URL(fileURLWithPath: trashPath))
            }
            NSApp.terminate(nil)
        }
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message.isEmpty ? "請稍後再試。" : message
        alert.addButton(withTitle: "好")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }
}

@main
private enum FamilyRecorderUninstallerMain {
    static func main() {
        let application = NSApplication.shared
        let delegate = UninstallerDelegate()
        application.delegate = delegate
        application.run()
        _ = delegate
    }
}
