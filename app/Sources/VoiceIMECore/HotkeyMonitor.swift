import ApplicationServices
import CoreGraphics
import Foundation
import os

/// 音声入力の起動キー方式。
public enum HotkeyMode: String, Codable, CaseIterable, Sendable, Equatable {
    /// fnキーを押している間だけ録音する（既定）。
    case fnHold
    /// Control + Option + Space を押すたびに開始・停止を切り替える。
    case controlOptionSpaceToggle

    /// メニューに表示する日本語名。
    public var displayName: String {
        switch self {
        case .fnHold:
            return "fnキーを押している間録音"
        case .controlOptionSpaceToggle:
            return "Control + Option + Space で開始/停止"
        }
    }
}

/// ホットキー状態機械が発火するアプリ操作。
public enum HotkeyAction: Sendable, Equatable {
    case startRecording
    case stopRecording
    case toggleRecording
    case cancelRecording
}

/// キーイベントに含まれる主要修飾キーの集合。
public struct HotkeyModifiers: OptionSet, Sendable, Equatable {
    public let rawValue: UInt8

    public init(rawValue: UInt8) {
        self.rawValue = rawValue
    }

    public static let fn = HotkeyModifiers(rawValue: 1 << 0)
    public static let command = HotkeyModifiers(rawValue: 1 << 1)
    public static let control = HotkeyModifiers(rawValue: 1 << 2)
    public static let option = HotkeyModifiers(rawValue: 1 << 3)
    public static let shift = HotkeyModifiers(rawValue: 1 << 4)

    public static let primaryModifiers: HotkeyModifiers = [.command, .control, .option, .shift]

    /// `CGEventFlags` から判定に必要な修飾キーだけを抽出する。
    public init(cgEventFlags flags: CGEventFlags) {
        var result: HotkeyModifiers = []
        if flags.contains(.maskSecondaryFn) { result.insert(.fn) }
        if flags.contains(.maskCommand) { result.insert(.command) }
        if flags.contains(.maskControl) { result.insert(.control) }
        if flags.contains(.maskAlternate) { result.insert(.option) }
        if flags.contains(.maskShift) { result.insert(.shift) }
        self = result
    }
}

/// `CGEventTap` から受け取る入力イベントの最小表現。
public enum HotkeyKeyEvent: Sendable, Equatable {
    case flagsChanged(flags: HotkeyModifiers)
    case keyDown(keyCode: UInt16, flags: HotkeyModifiers, isAutoRepeat: Bool)
}

/// ホットキーイベント処理の結果。
public struct HotkeyTransition: Sendable, Equatable {
    public let action: HotkeyAction?
    /// `true` のとき、`defaultTap` であればイベントを消費して前面アプリへ渡さない。
    public let shouldConsumeEvent: Bool

    public init(action: HotkeyAction?, shouldConsumeEvent: Bool) {
        self.action = action
        self.shouldConsumeEvent = shouldConsumeEvent
    }
}

/// `fn`長押し、`Control+Option+Space`トグル、`Esc`取り消しの状態遷移を担う純粋なステートマシン。
public struct HotkeyStateMachine: Sendable {
    public static let spaceKeyCode: UInt16 = 49
    public static let escapeKeyCode: UInt16 = 53

    public private(set) var mode: HotkeyMode
    private var isFnPressed = false
    private var fnSessionActive = false
    /// 録音中にEscで取り消した後、まだ押されているfnキーを離しても録音終了が発火しないようにするための抑制フラグ。
    private var fnSuppressedUntilRelease = false

    public init(mode: HotkeyMode = .fnHold) {
        self.mode = mode
    }

    /// 起動キー方式を切り替え、進行中のfn押下状態を初期化する。
    public mutating func setMode(_ newMode: HotkeyMode) {
        mode = newMode
        isFnPressed = false
        fnSessionActive = false
        fnSuppressedUntilRelease = false
    }

    /// 1件のキーイベントから発火すべき操作とイベント消費有無を返す。
    public mutating func handle(_ event: HotkeyKeyEvent, isRecording: Bool) -> HotkeyTransition {
        if case let .keyDown(keyCode, _, isAutoRepeat) = event,
           keyCode == Self.escapeKeyCode,
           !isAutoRepeat,
           isRecording {
            if mode == .fnHold && isFnPressed {
                fnSuppressedUntilRelease = true
                fnSessionActive = false
            }
            return HotkeyTransition(action: .cancelRecording, shouldConsumeEvent: true)
        }

        switch mode {
        case .fnHold:
            return handleFnHold(event)
        case .controlOptionSpaceToggle:
            return handleControlOptionSpace(event)
        }
    }

    private mutating func handleFnHold(_ event: HotkeyKeyEvent) -> HotkeyTransition {
        guard case let .flagsChanged(flags) = event else {
            return HotkeyTransition(action: nil, shouldConsumeEvent: false)
        }

        let hasFn = flags.contains(.fn)
        let hasPrimaryModifiers = !flags.intersection(.primaryModifiers).isEmpty

        if !isFnPressed && hasFn {
            isFnPressed = true
            if !hasPrimaryModifiers {
                fnSuppressedUntilRelease = false
                fnSessionActive = true
                return HotkeyTransition(action: .startRecording, shouldConsumeEvent: false)
            } else {
                fnSessionActive = false
                return HotkeyTransition(action: nil, shouldConsumeEvent: false)
            }
        }

        if isFnPressed && !hasFn {
            isFnPressed = false
            let shouldStop = fnSessionActive && !fnSuppressedUntilRelease
            fnSessionActive = false
            fnSuppressedUntilRelease = false
            return HotkeyTransition(
                action: shouldStop ? .stopRecording : nil,
                shouldConsumeEvent: false
            )
        }

        return HotkeyTransition(action: nil, shouldConsumeEvent: false)
    }

    private mutating func handleControlOptionSpace(_ event: HotkeyKeyEvent) -> HotkeyTransition {
        guard case let .keyDown(keyCode, flags, isAutoRepeat) = event,
              keyCode == Self.spaceKeyCode,
              !isAutoRepeat else {
            return HotkeyTransition(action: nil, shouldConsumeEvent: false)
        }

        let primary = flags.intersection(.primaryModifiers)
        if primary == [.control, .option] {
            return HotkeyTransition(action: .toggleRecording, shouldConsumeEvent: true)
        }
        return HotkeyTransition(action: nil, shouldConsumeEvent: false)
    }
}

/// ホットキー監視の抽象インターフェース。
@MainActor
public protocol HotkeyMonitoring: AnyObject {
    var mode: HotkeyMode { get set }
    var isRecordingProvider: (() -> Bool)? { get set }
    var onAction: ((HotkeyAction) -> Void)? { get set }
    @discardableResult
    func start() -> Bool
    func stop()
}

/// `CFMachPort` と `CFRunLoopSource` の破棄を一元管理する内部ハンドル。
private final class EventTapHandle: @unchecked Sendable {
    let tap: CFMachPort
    let source: CFRunLoopSource
    private let invalidated = OSAllocatedUnfairLock(initialState: false)

    init(tap: CFMachPort, source: CFRunLoopSource) {
        self.tap = tap
        self.source = source
    }

    func invalidate() {
        let shouldClean = invalidated.withLock { flag -> Bool in
            if flag { return false }
            flag = true
            return true
        }
        guard shouldClean else { return }
        CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: false)
        CFMachPortInvalidate(tap)
    }

    deinit {
        invalidate()
    }
}

/// `CGEventTap` でシステム全体の `flagsChanged` と `keyDown` を監視するホットキーモニター。
@MainActor
public final class CGEventTapHotkeyMonitor: HotkeyMonitoring {
    private nonisolated static let logger = Logger(subsystem: "com.voiceime.app", category: "HotkeyMonitor")

    public var mode: HotkeyMode {
        didSet {
            stateMachine.setMode(mode)
        }
    }

    public var isRecordingProvider: (() -> Bool)?
    public var onAction: ((HotkeyAction) -> Void)?

    private var stateMachine: HotkeyStateMachine
    private var tapHandle: EventTapHandle?
    private var isListenOnly = false

    public init(mode: HotkeyMode = .fnHold) {
        self.mode = mode
        self.stateMachine = HotkeyStateMachine(mode: mode)
    }

    deinit {
        tapHandle?.invalidate()
    }

    /// イベントタップを開始する。権限不足などで作成できない場合は `false` を返す。
    @discardableResult
    public func start() -> Bool {
        stop()

        let mask = (CGEventMask(1) << CGEventType.flagsChanged.rawValue)
            | (CGEventMask(1) << CGEventType.keyDown.rawValue)
        let userInfo = Unmanaged.passUnretained(self).toOpaque()

        // まずイベント消費が可能な defaultTap を試し、アクセシビリティ未許可時は listenOnly へフォールバックする。
        var tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: mask,
            callback: Self.eventTapCallback,
            userInfo: userInfo
        )
        var listenOnly = false
        if tap == nil {
            tap = CGEvent.tapCreate(
                tap: .cgSessionEventTap,
                place: .headInsertEventTap,
                options: .listenOnly,
                eventsOfInterest: mask,
                callback: Self.eventTapCallback,
                userInfo: userInfo
            )
            listenOnly = (tap != nil)
        }

        guard let tap else {
            Self.logger.error("CGEventTapを作成できませんでした。入力監視権限を確認してください。")
            return false
        }

        guard let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0) else {
            CFMachPortInvalidate(tap)
            return false
        }

        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        self.tapHandle = EventTapHandle(tap: tap, source: source)
        self.isListenOnly = listenOnly
        return true
    }

    /// イベントタップを停止し、RunLoopリソースを解放する。
    public func stop() {
        tapHandle?.invalidate()
        tapHandle = nil
        stateMachine.setMode(mode)
    }

    /// タップイベントを処理し、イベントを消費して前面アプリへ渡さない場合は `true` を返す。
    private func processTapEvent(type: CGEventType, keyEvent: HotkeyKeyEvent?) -> Bool {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let tap = tapHandle?.tap {
                CGEvent.tapEnable(tap: tap, enable: true)
                Self.logger.notice("無効化されたCGEventTapを再有効化しました。")
            }
            return false
        }

        guard let keyEvent else {
            return false
        }

        let recording = isRecordingProvider?() ?? false
        let transition = stateMachine.handle(keyEvent, isRecording: recording)

        if let action = transition.action {
            // タップコールバック自体をブロックしないよう、アクション実行は次ターンへ非同期ディスパッチする。
            Task { @MainActor [weak self] in
                self?.onAction?(action)
            }
        }

        return transition.shouldConsumeEvent && !isListenOnly
    }

    private static let eventTapCallback: CGEventTapCallBack = { _, type, event, userInfo in
        guard let userInfo else {
            return Unmanaged.passUnretained(event)
        }

        let keyEvent: HotkeyKeyEvent?
        switch type {
        case .flagsChanged:
            keyEvent = .flagsChanged(flags: HotkeyModifiers(cgEventFlags: event.flags))
        case .keyDown:
            let keyCode = UInt16(truncatingIfNeeded: event.getIntegerValueField(.keyboardEventKeycode))
            let isRepeat = event.getIntegerValueField(.keyboardEventAutorepeat) != 0
            keyEvent = .keyDown(
                keyCode: keyCode,
                flags: HotkeyModifiers(cgEventFlags: event.flags),
                isAutoRepeat: isRepeat
            )
        default:
            keyEvent = nil
        }

        let monitor = Unmanaged<CGEventTapHotkeyMonitor>.fromOpaque(userInfo).takeUnretainedValue()
        // CGEventTapのRunLoopソースはメインRunLoopへ登録しているためメインスレッド上で安全に実行される。
        let shouldConsume = MainActor.assumeIsolated {
            monitor.processTapEvent(type: type, keyEvent: keyEvent)
        }
        return shouldConsume ? nil : Unmanaged.passUnretained(event)
    }
}
