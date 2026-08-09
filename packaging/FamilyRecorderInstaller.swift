import AppKit
import Foundation

private struct WhisperChoice {
    let id: String
    let title: String
    let detail: String
}

private final class InstallerDelegate: NSObject, NSApplicationDelegate {
    private let models = [
        WhisperChoice(
            id: "small",
            title: "Small — 輕量快速",
            detail: "約 466 MB。適合記憶體較少、優先考量速度的 Mac。"
        ),
        WhisperChoice(
            id: "medium",
            title: "Medium — 平衡",
            detail: "約 1.5 GB。速度與中文辨識品質較平衡。"
        ),
        WhisperChoice(
            id: "large-v3-turbo",
            title: "Large v3 Turbo — 建議",
            detail: "約 1.6 GB。中文辨識品質較佳，Apple Silicon 以 Metal 加速。"
        ),
    ]

    private var window: NSWindow!
    private let architectureStatus = NSTextField(labelWithString: "檢查中…")
    private let homebrewStatus = NSTextField(labelWithString: "檢查中…")
    private let codexStatus = NSTextField(labelWithString: "檢查中…")
    private let authStatus = NSTextField(labelWithString: "檢查中…")
    private let modelPopup = NSPopUpButton(frame: .zero, pullsDown: false)
    private let modelDescription = NSTextField(wrappingLabelWithString: "")
    private let logView = NSTextView(frame: .zero)
    private let progress = NSProgressIndicator(frame: .zero)
    private let recheckButton = NSButton(title: "重新檢查", target: nil, action: nil)
    private let homebrewButton = NSButton(title: "取得 Homebrew", target: nil, action: nil)
    private let installCodexButton = NSButton(title: "安裝官方 Codex CLI", target: nil, action: nil)
    private let loginButton = NSButton(title: "登入 ChatGPT", target: nil, action: nil)
    private let deviceLoginButton = NSButton(title: "改用裝置碼登入", target: nil, action: nil)
    private let installButton = NSButton(title: "安裝 FamilyRecorder", target: nil, action: nil)
    private var activeProcess: Process?
    private var environment: [String: String] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildWindow()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        refreshEnvironment()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 720, height: 730),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.title = "安裝 FamilyRecorder"
        window.isReleasedWhenClosed = false

        let title = NSTextField(labelWithString: "FamilyRecorder")
        title.font = .systemFont(ofSize: 28, weight: .bold)
        let subtitle = NSTextField(
            wrappingLabelWithString: "XVF3800 本機 Whisper 轉錄＋ChatGPT 每日純文字摘要"
        )
        subtitle.font = .systemFont(ofSize: 15, weight: .medium)
        subtitle.textColor = .secondaryLabelColor

        let privacy = NSTextField(
            wrappingLabelWithString: "原始音訊留在這台 Mac；每日摘要只傳送文字。錄音前請先取得所有人的明確同意。"
        )
        privacy.textColor = .secondaryLabelColor

        let statusBox = NSBox()
        statusBox.title = "1. 系統與登入狀態"
        statusBox.contentView = statusContent()

        let modelBox = NSBox()
        modelBox.title = "2. 選擇本機 Whisper 模型"
        modelBox.contentView = modelContent()

        progress.style = .spinning
        progress.controlSize = .small
        progress.isDisplayedWhenStopped = false

        installButton.target = self
        installButton.action = #selector(installFamilyRecorder)
        installButton.bezelStyle = .rounded
        installButton.keyEquivalent = "\r"
        installButton.contentTintColor = .controlAccentColor

        let installRow = NSStackView(views: [progress, installButton])
        installRow.orientation = .horizontal
        installRow.alignment = .centerY
        installRow.spacing = 10
        installRow.distribution = .gravityAreas

        let logTitle = NSTextField(labelWithString: "安裝進度")
        logTitle.font = .systemFont(ofSize: 13, weight: .semibold)
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        scroll.documentView = logView
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.heightAnchor.constraint(equalToConstant: 170).isActive = true
        logView.isEditable = false
        logView.isSelectable = true
        logView.font = .monospacedSystemFont(ofSize: 11.5, weight: .regular)
        logView.backgroundColor = NSColor.textBackgroundColor
        logView.textContainerInset = NSSize(width: 8, height: 8)

        let footer = NSTextField(
            wrappingLabelWithString: "模型與 Homebrew 套件會從官方來源下載。Codex 登入由 OpenAI 官方 CLI 開啟瀏覽器處理，FamilyRecorder 不會讀取 token。"
        )
        footer.font = .systemFont(ofSize: 11)
        footer.textColor = .tertiaryLabelColor

        let stack = NSStackView(views: [
            title, subtitle, privacy, statusBox, modelBox, installRow, logTitle, scroll, footer,
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        guard let content = window.contentView else { return }
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 24),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: content.bottomAnchor, constant: -20),
            statusBox.widthAnchor.constraint(equalTo: stack.widthAnchor),
            modelBox.widthAnchor.constraint(equalTo: stack.widthAnchor),
            installRow.widthAnchor.constraint(equalTo: stack.widthAnchor),
            scroll.widthAnchor.constraint(equalTo: stack.widthAnchor),
            privacy.widthAnchor.constraint(equalTo: stack.widthAnchor),
            footer.widthAnchor.constraint(equalTo: stack.widthAnchor),
        ])
    }

    private func statusContent() -> NSView {
        let architectureLabel = NSTextField(labelWithString: "Mac")
        let homebrewLabel = NSTextField(labelWithString: "Homebrew")
        let codexLabel = NSTextField(labelWithString: "Codex CLI")
        let authLabel = NSTextField(labelWithString: "ChatGPT 登入")
        for label in [architectureLabel, homebrewLabel, codexLabel, authLabel] {
            label.font = .systemFont(ofSize: 12, weight: .semibold)
        }

        let grid = NSGridView(views: [
            [architectureLabel, architectureStatus],
            [homebrewLabel, homebrewStatus],
            [codexLabel, codexStatus],
            [authLabel, authStatus],
        ])
        grid.rowSpacing = 5
        grid.columnSpacing = 14
        grid.column(at: 0).xPlacement = .trailing
        grid.column(at: 1).xPlacement = .leading

        recheckButton.target = self
        recheckButton.action = #selector(refreshEnvironment)
        homebrewButton.target = self
        homebrewButton.action = #selector(openHomebrew)
        installCodexButton.target = self
        installCodexButton.action = #selector(installCodex)
        loginButton.target = self
        loginButton.action = #selector(loginCodex)
        deviceLoginButton.target = self
        deviceLoginButton.action = #selector(deviceLoginCodex)
        deviceLoginButton.bezelStyle = .inline

        let buttons = NSStackView(views: [
            recheckButton, homebrewButton, installCodexButton, loginButton, deviceLoginButton,
        ])
        buttons.orientation = .horizontal
        buttons.alignment = .centerY
        buttons.spacing = 8

        let stack = NSStackView(views: [grid, buttons])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        let content = NSView()
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor, constant: -14),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 10),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
        ])
        return content
    }

    private func modelContent() -> NSView {
        modelPopup.addItems(withTitles: models.map(\.title))
        modelPopup.selectItem(at: 2)
        modelPopup.target = self
        modelPopup.action = #selector(modelChanged)
        modelDescription.stringValue = models[2].detail
        modelDescription.textColor = .secondaryLabelColor

        let stack = NSStackView(views: [modelPopup, modelDescription])
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
            modelPopup.widthAnchor.constraint(greaterThanOrEqualToConstant: 260),
        ])
        return content
    }

    @objc private func modelChanged() {
        let index = max(0, modelPopup.indexOfSelectedItem)
        modelDescription.stringValue = models[index].detail
    }

    private func helperPath() -> String? {
        Bundle.main.url(forResource: "install_payload", withExtension: "sh")?.path
    }

    private func setBusy(_ busy: Bool) {
        if busy {
            progress.startAnimation(nil)
        } else {
            progress.stopAnimation(nil)
        }
        for button in [
            recheckButton, homebrewButton, installCodexButton, loginButton, deviceLoginButton,
            installButton,
        ] {
            button.isEnabled = !busy
        }
        modelPopup.isEnabled = !busy
    }

    private func appendLog(_ message: String) {
        guard !message.isEmpty else { return }
        let normalized = message.hasSuffix("\n") ? message : message + "\n"
        logView.textStorage?.append(NSAttributedString(string: normalized))
        logView.scrollToEndOfDocument(nil)
    }

    private func parseEnvironment(_ output: String) {
        var values: [String: String] = [:]
        for line in output.split(separator: "\n", omittingEmptySubsequences: true) {
            let parts = line.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            if parts.count == 2 {
                values[String(parts[0])] = String(parts[1])
            }
        }
        environment = values
        let arm64 = values["ARCH"] == "arm64"
        architectureStatus.stringValue = arm64
            ? "✓ Apple Silicon，macOS \(values["MACOS"] ?? "")"
            : "✗ 此安裝包只支援 Apple Silicon"
        architectureStatus.textColor = arm64 ? .systemGreen : .systemRed

        let hasHomebrew = !(values["HOMEBREW"] ?? "").isEmpty
        homebrewStatus.stringValue = hasHomebrew ? "✓ 已安裝" : "✗ 尚未安裝"
        homebrewStatus.textColor = hasHomebrew ? .systemGreen : .systemOrange
        homebrewButton.isHidden = hasHomebrew

        let hasCodex = !(values["CODEX"] ?? "").isEmpty
        codexStatus.stringValue = hasCodex ? "✓ 已安裝" : "尚未安裝（摘要功能需要）"
        codexStatus.textColor = hasCodex ? .systemGreen : .secondaryLabelColor
        installCodexButton.isHidden = hasCodex

        let authenticated = values["CODEX_AUTH"] == "1"
        authStatus.stringValue = authenticated
            ? "✓ 已用 ChatGPT 登入"
            : (hasCodex ? "尚未登入" : "請先安裝 Codex CLI")
        authStatus.textColor = authenticated ? .systemGreen : .systemOrange
        loginButton.isEnabled = hasCodex
        deviceLoginButton.isEnabled = hasCodex
        deviceLoginButton.isHidden = !hasCodex || authenticated
        installButton.isEnabled = arm64 && hasHomebrew
    }

    private func runHelper(
        _ arguments: [String],
        showOutput: Bool = true,
        completion: @escaping (Int32, String) -> Void
    ) {
        guard activeProcess == nil else { return }
        guard let helper = helperPath() else {
            showAlert(title: "安裝包不完整", message: "找不到 install_payload.sh。")
            return
        }
        setBusy(true)
        let process = Process()
        let pipe = Pipe()
        let captureQueue = DispatchQueue(label: "com.familyrecorder.installer.output")
        var captured = Data()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [helper] + arguments
        process.standardOutput = pipe
        process.standardError = pipe
        process.environment = ProcessInfo.processInfo.environment
        activeProcess = process

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else {
                handle.readabilityHandler = nil
                return
            }
            captureQueue.sync { captured.append(data) }
            if showOutput, let text = String(data: data, encoding: .utf8) {
                DispatchQueue.main.async { self?.appendLog(text) }
            }
        }
        process.terminationHandler = { [weak self] finished in
            pipe.fileHandleForReading.readabilityHandler = nil
            let remaining = pipe.fileHandleForReading.readDataToEndOfFile()
            captureQueue.sync { captured.append(remaining) }
            let output = captureQueue.sync {
                String(data: captured, encoding: .utf8) ?? ""
            }
            DispatchQueue.main.async {
                self?.activeProcess = nil
                self?.setBusy(false)
                completion(finished.terminationStatus, output)
            }
        }
        do {
            try process.run()
        } catch {
            pipe.fileHandleForReading.readabilityHandler = nil
            activeProcess = nil
            setBusy(false)
            completion(1, error.localizedDescription)
        }
    }

    @objc private func refreshEnvironment() {
        runHelper(["preflight"], showOutput: false) { [weak self] status, output in
            guard let self else { return }
            if status == 0 {
                self.parseEnvironment(output)
                self.appendLog("環境檢查完成。")
            } else {
                self.appendLog(output)
                self.showAlert(title: "環境檢查失敗", message: output)
            }
        }
    }

    @objc private func openHomebrew() {
        guard let url = URL(string: "https://brew.sh/") else { return }
        NSWorkspace.shared.open(url)
    }

    @objc private func installCodex() {
        appendLog("\n— 安裝官方 Codex CLI —")
        runHelper(["install-codex"]) { [weak self] status, output in
            guard let self else { return }
            if status != 0 {
                self.showAlert(title: "Codex CLI 安裝失敗", message: output)
            }
            self.refreshEnvironment()
        }
    }

    @objc private func loginCodex() {
        appendLog("\n— ChatGPT 網頁登入 —")
        runHelper(["codex-login"]) { [weak self] status, output in
            guard let self else { return }
            if status != 0 {
                self.showAlert(
                    title: "登入尚未完成",
                    message: output + "\n若瀏覽器登入無法返回，可改用「裝置碼登入」。"
                )
            }
            self.refreshEnvironment()
        }
    }

    @objc private func deviceLoginCodex() {
        appendLog("\n— ChatGPT 裝置碼登入 —")
        runHelper(["codex-device-login"]) { [weak self] status, output in
            guard let self else { return }
            if status != 0 {
                self.showAlert(title: "裝置碼登入尚未完成", message: output)
            }
            self.refreshEnvironment()
        }
    }

    @objc private func installFamilyRecorder() {
        let index = max(0, modelPopup.indexOfSelectedItem)
        let model = models[index]
        let confirmation = NSAlert()
        confirmation.messageText = "安裝 FamilyRecorder？"
        confirmation.informativeText =
            "將安裝 \(model.title)，下載 Homebrew 套件與 Whisper 模型，並啟用登入後常駐錄音。原有設定若存在會先備份。"
        confirmation.addButton(withTitle: "開始安裝")
        confirmation.addButton(withTitle: "取消")
        NSApp.activate(ignoringOtherApps: true)
        guard confirmation.runModal() == .alertFirstButtonReturn else { return }

        appendLog("\n— 安裝 FamilyRecorder（\(model.id)）—")
        runHelper(["install", model.id]) { [weak self] status, output in
            guard let self else { return }
            if status == 0 {
                let alert = NSAlert()
                alert.messageText = "FamilyRecorder 安裝完成"
                alert.informativeText =
                    "請接上 XVF3800，並允許 macOS 麥克風權限。右上角出現波形圖示後即可操作。"
                alert.addButton(withTitle: "打開麥克風設定")
                alert.addButton(withTitle: "完成")
                NSApp.activate(ignoringOtherApps: true)
                if alert.runModal() == .alertFirstButtonReturn,
                   let url = URL(
                       string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
                   )
                {
                    NSWorkspace.shared.open(url)
                }
            } else {
                self.showAlert(title: "安裝未完成", message: output)
            }
            self.refreshEnvironment()
        }
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message.isEmpty ? "請查看安裝進度。" : message
        alert.addButton(withTitle: "好")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }
}

@main
private enum FamilyRecorderInstallerMain {
    static func main() {
        let application = NSApplication.shared
        let delegate = InstallerDelegate()
        application.delegate = delegate
        application.run()
        _ = delegate
    }
}
