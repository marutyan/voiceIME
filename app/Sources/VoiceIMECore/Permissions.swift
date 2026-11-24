import AVFoundation
import ApplicationServices
import CoreGraphics
import Foundation

/// VoiceIMEの動作に必要なmacOSのプライバシー権限。
public enum RequiredPermission: String, CaseIterable, Sendable, Equatable {
    case microphone
    case accessibility
    case inputMonitoring

    /// ユーザーへ表示する権限名。
    public var displayName: String {
        switch self {
        case .microphone:
            return "マイク"
        case .accessibility:
            return "アクセシビリティ"
        case .inputMonitoring:
            return "入力監視"
        }
    }

    /// システム設定で許可する場所と理由の案内文。
    public var guidanceMessage: String {
        switch self {
        case .microphone:
            return "マイクの権限がありません。「システム設定 > プライバシーとセキュリティ > マイク」で VoiceIME を許可してください。"
        case .accessibility:
            return "アクセシビリティの権限がありません。「システム設定 > プライバシーとセキュリティ > アクセシビリティ」で VoiceIME を許可してください（入力先の照合と貼り付けに必要です）。"
        case .inputMonitoring:
            return "入力監視の権限がありません。「システム設定 > プライバシーとセキュリティ > 入力監視」で VoiceIME を許可してください（起動キーの監視に必要です）。"
        }
    }
}

/// 各権限の許可状態をまとめたスナップショット。
public struct PermissionStatus: Sendable, Equatable {
    /// 任意機能（「画面の文字を使う」）の画面収録権限が未許可のときに案内するメッセージ。
    public static let screenRecordingGuidanceMessage =
        "画面収録の権限がありません。「システム設定 > プライバシーとセキュリティ > 画面収録とシステムオーディオ録音」で VoiceIME を許可してから再起動してください。"

    public let microphone: Bool
    public let accessibility: Bool
    public let inputMonitoring: Bool
    /// 任意機能（「画面の文字を使う」）で前面ウィンドウを読むための画面収録権限。未許可でも音声入力自体は継続する。
    public let screenRecording: Bool

    public init(
        microphone: Bool,
        accessibility: Bool,
        inputMonitoring: Bool,
        screenRecording: Bool = false
    ) {
        self.microphone = microphone
        self.accessibility = accessibility
        self.inputMonitoring = inputMonitoring
        self.screenRecording = screenRecording
    }

    /// 音声入力の基本動作に必須の未許可権限一覧を返す（画面収録は任意機能のため含めない）。
    public var missingPermissions: [RequiredPermission] {
        var missing: [RequiredPermission] = []
        if !microphone { missing.append(.microphone) }
        if !accessibility { missing.append(.accessibility) }
        if !inputMonitoring { missing.append(.inputMonitoring) }
        return missing
    }

    /// 不足している必須権限すべてを1通の通知本文へまとめる。
    public func missingSummaryMessage() -> String? {
        let missing = missingPermissions
        guard !missing.isEmpty else { return nil }
        if missing.count == 1 {
            return missing[0].guidanceMessage
        }
        let paths = missing.map { "・システム設定 > プライバシーとセキュリティ > \($0.displayName)" }
            .joined(separator: "\n")
        return "以下の権限が許可されていません。VoiceIME を許可してから再起動してください。\n\(paths)"
    }
}

/// 権限確認の抽象化。実機ではmacOS APIを呼び、テストでは状態を差し替える。
public protocol PermissionChecking: Sendable {
    func currentStatus() -> PermissionStatus
    func requestMicrophonePermissionIfNeeded() async -> Bool
    @discardableResult
    func requestScreenRecordingPermission() -> Bool
}

public extension PermissionChecking {
    @discardableResult
    func requestScreenRecordingPermission() -> Bool {
        currentStatus().screenRecording
    }
}

/// macOS標準APIを用いてマイク・アクセシビリティ・入力監視・画面収録の権限を確認するチェッカー。
public struct SystemPermissionChecker: PermissionChecking {
    public init() {}

    public func currentStatus() -> PermissionStatus {
        let mic = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
        let ax = AXIsProcessTrusted()
        let input = CGPreflightListenEventAccess()
        let screen = CGPreflightScreenCaptureAccess()
        return PermissionStatus(
            microphone: mic,
            accessibility: ax,
            inputMonitoring: input,
            screenRecording: screen
        )
    }

    public func requestMicrophonePermissionIfNeeded() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: .audio)
        case .denied, .restricted:
            return false
        @unknown default:
            return false
        }
    }

    /// 画面収録権限が未許可の場合に、システム設定への登録・許可確認を促す。
    @discardableResult
    public func requestScreenRecordingPermission() -> Bool {
        if CGPreflightScreenCaptureAccess() {
            return true
        }
        return CGRequestScreenCaptureAccess()
    }
}
