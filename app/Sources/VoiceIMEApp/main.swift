import AppKit
import Darwin
import Foundation
import VoiceIMECore

/// メニューバーアイコンの状態表示と最小限のメニュー操作を担うアプリデリゲート。
@MainActor
final class MenuBarAppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var statusItem: NSStatusItem?
    private let statusLineItem = NSMenuItem(title: "状態: 起動中...", action: nil, keyEquivalent: "")
    private let fnHoldMenuItem = NSMenuItem(
        title: HotkeyMode.fnHold.displayName,
        action: #selector(selectFnHoldMode),
        keyEquivalent: ""
    )
    private let toggleModeMenuItem = NSMenuItem(
        title: HotkeyMode.controlOptionSpaceToggle.displayName,
        action: #selector(selectToggleMode),
        keyEquivalent: ""
    )
    private let overlayMenuItem = NSMenuItem(
        title: OverlayMetrics.menuTitle(isEnabled: true),
        action: #selector(toggleOverlay),
        keyEquivalent: ""
    )
    private let screenTextMenuItem = NSMenuItem(
        title: ScreenTextStatus.enabled.menuTitle,
        action: #selector(toggleScreenText),
        keyEquivalent: ""
    )
    private let screenPermissionMenuItem = NSMenuItem(
        title: "画面収録の権限を確認...",
        action: #selector(requestScreenRecordingPermission),
        keyEquivalent: ""
    )
    private let repasteMenuItem = NSMenuItem(
        title: "最後の結果をもう一度貼る",
        action: #selector(repasteLastResult),
        keyEquivalent: ""
    )

    private var coordinator: AppCoordinator?
    private let notifier = SystemUserNotifier()
    private let overlayController = OverlayPanelController()

    func applicationDidFinishLaunching(_ notification: Notification) {
        signal(SIGPIPE, SIG_IGN)
        setupStatusItem()

        do {
            let launchConfig = try EngineLaunchConfig.resolveDefault()
            let engineClient = EngineClient(launchConfig: launchConfig)
            let coordinator = AppCoordinator(
                engineClient: engineClient,
                notifier: notifier
            )
            coordinator.onUIStateChange = { [weak self] state in
                self?.render(state)
            }
            coordinator.onAudioLevelChange = { [weak self] level in
                self?.overlayController.updateAudioLevel(level)
            }
            self.coordinator = coordinator
            render(coordinator.uiState)
            coordinator.start()
        } catch {
            let overlayEnabled = UserDefaults.standard.object(forKey: AppCoordinator.overlayEnabledDefaultsKey) == nil
                ? true
                : UserDefaults.standard.bool(forKey: AppCoordinator.overlayEnabledDefaultsKey)
            let fallbackState = AppUIState(
                iconState: .error,
                statusText: "起動設定エラー",
                hotkeyMode: .fnHold,
                isOverlayEnabled: overlayEnabled,
                overlayState: overlayEnabled ? .error(message: "起動設定エラー") : .hidden,
                lastResultText: nil
            )
            render(fallbackState)
            if overlayEnabled {
                Task { [weak self] in
                    try? await Task.sleep(for: OverlayMetrics.errorAutoHideDelay)
                    self?.overlayController.update(state: .hidden)
                }
            }
            notifier.requestAuthorizationIfAvailable()
            notifier.notify(title: "VoiceIME 起動エラー", body: error.localizedDescription)
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        overlayController.hideImmediately()
        coordinator?.stopSynchronouslyForAppTermination()
    }

    func menuWillOpen(_ menu: NSMenu) {
        coordinator?.refreshScreenRecordingPermission()
    }

    private func setupStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem = item

        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.delegate = self

        statusLineItem.isEnabled = false
        menu.addItem(statusLineItem)
        menu.addItem(.separator())

        let hotkeyHeader = NSMenuItem(title: "起動キー", action: nil, keyEquivalent: "")
        hotkeyHeader.isEnabled = false
        menu.addItem(hotkeyHeader)

        fnHoldMenuItem.target = self
        menu.addItem(fnHoldMenuItem)

        toggleModeMenuItem.target = self
        menu.addItem(toggleModeMenuItem)

        menu.addItem(.separator())

        overlayMenuItem.target = self
        menu.addItem(overlayMenuItem)

        screenTextMenuItem.target = self
        menu.addItem(screenTextMenuItem)

        screenPermissionMenuItem.target = self
        screenPermissionMenuItem.isHidden = true
        menu.addItem(screenPermissionMenuItem)

        menu.addItem(.separator())

        repasteMenuItem.target = self
        repasteMenuItem.isEnabled = false
        menu.addItem(repasteMenuItem)

        menu.addItem(.separator())

        let quitItem = NSMenuItem(
            title: "終了",
            action: #selector(quitApplication),
            keyEquivalent: "q"
        )
        quitItem.target = self
        menu.addItem(quitItem)

        item.menu = menu
    }

    private func render(_ state: AppUIState) {
        statusLineItem.title = "状態: \(state.statusText)"
        fnHoldMenuItem.state = (state.hotkeyMode == .fnHold) ? .on : .off
        toggleModeMenuItem.state = (state.hotkeyMode == .controlOptionSpaceToggle) ? .on : .off
        overlayMenuItem.title = OverlayMetrics.menuTitle(isEnabled: state.isOverlayEnabled)
        overlayMenuItem.state = state.isOverlayEnabled ? .on : .off
        overlayMenuItem.isEnabled = (coordinator != nil)
        screenTextMenuItem.title = state.screenTextStatus.menuTitle
        screenTextMenuItem.state = (state.screenTextStatus == .enabled) ? .on : .off
        screenTextMenuItem.isEnabled = (coordinator != nil)
        screenPermissionMenuItem.isHidden = (coordinator == nil || state.screenTextStatus != .permissionMissing)
        repasteMenuItem.isEnabled = (state.lastResultText?.isEmpty == false)
        updateStatusIcon(state.iconState)
        overlayController.update(state: state.overlayState)
    }

    private func updateStatusIcon(_ iconState: AppIconState) {
        guard let button = statusItem?.button else { return }

        let symbolName: String
        let accessibilityLabel: String
        let tintColor: NSColor?

        switch iconState {
        case .idle:
            symbolName = "mic"
            accessibilityLabel = "VoiceIME 待機中"
            tintColor = nil
        case .recording:
            symbolName = "mic.fill"
            accessibilityLabel = "VoiceIME 録音中"
            tintColor = .systemRed
        case .processing:
            symbolName = "waveform"
            accessibilityLabel = "VoiceIME 処理中"
            tintColor = nil
        case .error:
            symbolName = "exclamationmark.triangle.fill"
            accessibilityLabel = "VoiceIME エラー"
            tintColor = .systemOrange
        }

        if let baseImage = NSImage(
            systemSymbolName: symbolName,
            accessibilityDescription: accessibilityLabel
        ) {
            if let tintColor {
                let config = NSImage.SymbolConfiguration(paletteColors: [tintColor])
                let colored = baseImage.withSymbolConfiguration(config) ?? baseImage
                colored.isTemplate = false
                button.image = colored
            } else {
                baseImage.isTemplate = true
                button.image = baseImage
            }
            button.title = ""
        } else {
            button.image = nil
            button.title = "VoiceIME"
        }
    }

    @objc private func selectFnHoldMode() {
        coordinator?.setHotkeyMode(.fnHold)
    }

    @objc private func selectToggleMode() {
        coordinator?.setHotkeyMode(.controlOptionSpaceToggle)
    }

    @objc private func toggleOverlay() {
        coordinator?.toggleOverlayEnabled()
    }

    @objc private func toggleScreenText() {
        coordinator?.toggleScreenTextEnabled()
    }

    @objc private func requestScreenRecordingPermission() {
        coordinator?.requestScreenRecordingPermission()
    }

    @objc private func repasteLastResult() {
        coordinator?.repasteLastResult()
    }

    @objc private func quitApplication() {
        NSApplication.shared.terminate(nil)
    }
}

let app = NSApplication.shared
// Dockアイコンを表示せずメニューバー常駐アプリとして動作させる。
app.setActivationPolicy(.accessory)
let delegate = MenuBarAppDelegate()
app.delegate = delegate
app.run()
