import CoreGraphics
import Foundation
import ScreenCaptureKit
import Vision
import os

/// ScreenCaptureKitから取得したウィンドウ一覧から前面ウィンドウを選ぶための軽量メタデータ。
public struct WindowCandidate: Sendable, Equatable {
    public let windowID: CGWindowID
    public let owningPid: pid_t?
    public let windowLayer: Int
    public let isOnScreen: Bool
    public let isActive: Bool
    public let frame: CGRect

    public init(
        windowID: CGWindowID,
        owningPid: pid_t?,
        windowLayer: Int,
        isOnScreen: Bool,
        isActive: Bool,
        frame: CGRect
    ) {
        self.windowID = windowID
        self.owningPid = owningPid
        self.windowLayer = windowLayer
        self.isOnScreen = isOnScreen
        self.isActive = isActive
        self.frame = frame
    }
}

/// 前面ウィンドウ1枚をメモリ上の `CGImage` として撮影する抽象インターフェース。
public protocol WindowImageCapturing: Sendable {
    func captureFrontmostWindow(preferredPid: pid_t?) async throws -> CGImage?
}

/// メモリ上の `CGImage` からテキスト行を読み取る抽象インターフェース。
public protocol ImageTextRecognizing: Sendable {
    func recognizeTextLines(in image: CGImage) async throws -> [String]
}

/// 録音開始時に前面ウィンドウの文字を時間上限付きで読み取る抽象インターフェース。
public protocol ScreenTextReading: Sendable {
    func readFrontmostWindowText(preferredPid: pid_t?, timeout: Duration) async -> String?
}

/// `ScreenCaptureKit`（`SCScreenshotManager`）で前面ウィンドウ1枚だけをメモリ上へ撮影する実装。画像はディスクへ保存しない。
public struct ScreenCaptureKitWindowCapturer: WindowImageCapturing {
    /// OCRの速度と細かい文字の判読性を両立するための撮影長辺の上限ピクセル数。
    public static let defaultMaxPixelDimension = 2_048
    /// 不可視の1x1補助ウィンドウ等を除外するための通常ウィンドウ最小サイズ（ポイント）。
    public static let minimumSubstantialWidth: CGFloat = 100
    public static let minimumSubstantialHeight: CGFloat = 80

    private let maxPixelDimension: Int
    private let ownPid: pid_t

    public init(
        maxPixelDimension: Int = defaultMaxPixelDimension,
        ownPid: pid_t = ProcessInfo.processInfo.processIdentifier
    ) {
        self.maxPixelDimension = max(1, maxPixelDimension)
        self.ownPid = ownPid
    }

    /// Zオーダー順（前面→背面）のウィンドウ候補から、撮影対象とする前面ウィンドウ1件を選ぶ。
    public static func selectFrontmostWindow(
        from candidates: [WindowCandidate],
        preferredPid: pid_t?,
        ownPid: pid_t
    ) -> WindowCandidate? {
        let normalWindows = candidates.filter { window in
            window.isOnScreen
                && window.windowLayer == 0
                && window.owningPid != ownPid
                && window.frame.width > 0
                && window.frame.height > 0
        }
        guard !normalWindows.isEmpty else { return nil }

        let substantialWindows = normalWindows.filter { window in
            window.frame.width >= minimumSubstantialWidth
                && window.frame.height >= minimumSubstantialHeight
        }

        if let preferredPid {
            if let match = substantialWindows.first(where: { $0.owningPid == preferredPid && $0.isActive }) {
                return match
            }
            if let match = substantialWindows.first(where: { $0.owningPid == preferredPid }) {
                return match
            }
            if let match = normalWindows.first(where: { $0.owningPid == preferredPid }) {
                return match
            }
        }

        if let active = substantialWindows.first(where: { $0.isActive }) {
            return active
        }
        if let frontSubstantial = substantialWindows.first {
            return frontSubstantial
        }
        return normalWindows.first
    }

    /// ウィンドウの論理サイズとスケール係数から、アスペクト比を保ち上限ピクセル数内に収まる出力サイズを計算する。
    public static func capturePixelSize(
        contentRect: CGRect,
        pointPixelScale: Float,
        maxDimension: Int = defaultMaxPixelDimension
    ) -> (width: Int, height: Int) {
        let safeScale = CGFloat(max(pointPixelScale, 1.0))
        let rawWidth = max(contentRect.width * safeScale, 1.0)
        let rawHeight = max(contentRect.height * safeScale, 1.0)
        let cap = CGFloat(max(maxDimension, 1))
        let longest = max(rawWidth, rawHeight)

        if longest <= cap {
            return (max(1, Int(rawWidth.rounded())), max(1, Int(rawHeight.rounded())))
        }
        let ratio = cap / longest
        let scaledWidth = max(1, Int((rawWidth * ratio).rounded()))
        let scaledHeight = max(1, Int((rawHeight * ratio).rounded()))
        return (scaledWidth, scaledHeight)
    }

    public func captureFrontmostWindow(preferredPid: pid_t?) async throws -> CGImage? {
        try Task.checkCancellation()
        let content = try await SCShareableContent.excludingDesktopWindows(
            true,
            onScreenWindowsOnly: true
        )
        try Task.checkCancellation()

        let candidates = content.windows.map { window in
            WindowCandidate(
                windowID: window.windowID,
                owningPid: window.owningApplication?.processID,
                windowLayer: window.windowLayer,
                isOnScreen: window.isOnScreen,
                isActive: window.isActive,
                frame: window.frame
            )
        }
        guard let selected = Self.selectFrontmostWindow(
            from: candidates,
            preferredPid: preferredPid,
            ownPid: ownPid
        ),
        let targetWindow = content.windows.first(where: { $0.windowID == selected.windowID }) else {
            return nil
        }

        let filter = SCContentFilter(desktopIndependentWindow: targetWindow)
        let rect = (filter.contentRect.width > 0 && filter.contentRect.height > 0)
            ? filter.contentRect
            : targetWindow.frame
        let pixelSize = Self.capturePixelSize(
            contentRect: rect,
            pointPixelScale: filter.pointPixelScale,
            maxDimension: maxPixelDimension
        )

        let config = SCStreamConfiguration()
        config.width = pixelSize.width
        config.height = pixelSize.height
        config.showsCursor = false
        config.scalesToFit = true
        config.captureResolution = .best

        try Task.checkCancellation()
        return try await SCScreenshotManager.captureImage(
            contentFilter: filter,
            configuration: config
        )
    }
}

/// `Vision` の `VNRecognizeTextRequest`（日本語・英語、精度優先）でメモリ上の画像から文字行を抽出する実装。
public final class VisionTextRecognizer: ImageTextRecognizing, Sendable {
    /// OCR対象の言語（日本語と英語）。
    public static let defaultRecognitionLanguages = ["ja-JP", "en-US"]

    private let languages: [String]
    /// 同期的なVision推論でSwiftの協調スレッドプールやメインスレッドを塞がないための専用キュー。
    private let ocrQueue = DispatchQueue(label: "com.voiceime.app.vision-ocr", qos: .userInitiated)

    public init(languages: [String] = defaultRecognitionLanguages) {
        self.languages = languages
    }

    /// 日本語・英語の精度優先設定を施した `VNRecognizeTextRequest` を生成する。
    internal static func makeRequest(
        languages: [String] = defaultRecognitionLanguages
    ) -> VNRecognizeTextRequest {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = languages
        request.usesLanguageCorrection = true
        return request
    }

    public func recognizeTextLines(in image: CGImage) async throws -> [String] {
        try Task.checkCancellation()
        let languages = self.languages
        let cancelled = OSAllocatedUnfairLock(initialState: false)
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                ocrQueue.async {
                    if cancelled.withLock({ $0 }) {
                        continuation.resume(throwing: CancellationError())
                        return
                    }
                    do {
                        let request = Self.makeRequest(languages: languages)
                        let handler = VNImageRequestHandler(cgImage: image, options: [:])
                        try handler.perform([request])
                        let lines = (request.results ?? []).compactMap { observation in
                            observation.topCandidates(1).first?.string
                        }
                        continuation.resume(returning: lines)
                    } catch {
                        continuation.resume(throwing: error)
                    }
                }
            }
        } onCancel: {
            cancelled.withLock { $0 = true }
        }
    }
}

/// 最初の一回だけ `CheckedContinuation` を安全に再開するためのスレッドセーフなゲート。
/// 協調キャンセルに応答しない処理が走っていても、タイムアウト時刻で即座に呼び出し元へ戻すために使う。
private final class TimeoutContinuationGate<Value: Sendable>: @unchecked Sendable {
    private enum State {
        case waiting
        case buffered(Value)
        case installed(CheckedContinuation<Value, Never>)
        case resumed
    }

    private let state = OSAllocatedUnfairLock(initialState: State.waiting)

    /// continuation を登録する。既に結果が決まっていればその場で再開する。
    func install(_ continuation: CheckedContinuation<Value, Never>) {
        let immediateValue: Value? = state.withLock { current in
            switch current {
            case .waiting:
                current = .installed(continuation)
                return nil
            case let .buffered(value):
                current = .resumed
                return value
            case .installed, .resumed:
                return nil
            }
        }
        if let immediateValue {
            continuation.resume(returning: immediateValue)
        }
    }

    /// 最初の1回だけ結果を採用し、登録済みの continuation を再開する。
    @discardableResult
    func resolve(with value: Value) -> Bool {
        let continuationToResume: CheckedContinuation<Value, Never>? = state.withLock { current in
            switch current {
            case .waiting:
                current = .buffered(value)
                return nil
            case let .installed(continuation):
                current = .resumed
                return continuation
            case .buffered, .resumed:
                return nil
            }
        }
        if let continuationToResume {
            continuationToResume.resume(returning: value)
            return true
        }
        return false
    }
}

/// 前面ウィンドウの撮影・文字認識・整形（4,000字上限）・時間切れ制御を統合するリーダー。
public final class ScreenTextReader: ScreenTextReading, Sendable {
    private static let logger = Logger(subsystem: "com.voiceime.app", category: "ScreenTextReader")

    private let capturer: WindowImageCapturing
    private let recognizer: ImageTextRecognizing
    private let maxLength: Int

    public init(
        capturer: WindowImageCapturing = ScreenCaptureKitWindowCapturer(),
        recognizer: ImageTextRecognizing = VisionTextRecognizer(),
        maxLength: Int = EngineScreenText.maxLength
    ) {
        self.capturer = capturer
        self.recognizer = recognizer
        self.maxLength = maxLength
    }

    /// 前面ウィンドウを撮影してOCRし、指定時間内に終わった場合のみ整形済み文字列を返す。
    /// 時間切れ・失敗・空結果・キャンセル時は `nil` を返し、録音を遅らせない。
    public func readFrontmostWindowText(
        preferredPid: pid_t?,
        timeout: Duration
    ) async -> String? {
        guard !Task.isCancelled, timeout > .zero else {
            return nil
        }

        let gate = TimeoutContinuationGate<String?>()
        let capturer = self.capturer
        let recognizer = self.recognizer
        let maxLength = self.maxLength

        let workTask = Task.detached(priority: .userInitiated) {
            do {
                guard !Task.isCancelled else {
                    gate.resolve(with: nil)
                    return
                }
                guard let image = try await capturer.captureFrontmostWindow(preferredPid: preferredPid) else {
                    gate.resolve(with: nil)
                    return
                }
                guard !Task.isCancelled else {
                    gate.resolve(with: nil)
                    return
                }
                let lines = try await recognizer.recognizeTextLines(in: image)
                guard !Task.isCancelled else {
                    gate.resolve(with: nil)
                    return
                }
                let formatted = EngineScreenText.format(lines: lines, maxLength: maxLength)
                gate.resolve(with: formatted)
            } catch is CancellationError {
                gate.resolve(with: nil)
            } catch {
                // プライバシー保護のため画面の文字列自体はログへ出さず、失敗理由だけを記録する。
                Self.logger.notice("前面ウィンドウの文字読み取りをスキップしました: \(error.localizedDescription, privacy: .public)")
                gate.resolve(with: nil)
            }
        }

        let timerTask = Task.detached(priority: .userInitiated) {
            do {
                try await Task.sleep(for: timeout)
                workTask.cancel()
                gate.resolve(with: nil)
            } catch {
                // 正常完了または親キャンセルによりタイマーが不要になった場合はそのまま終了する。
            }
        }

        let result = await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                gate.install(continuation)
            }
        } onCancel: {
            workTask.cancel()
            timerTask.cancel()
            gate.resolve(with: nil)
        }

        timerTask.cancel()
        return result
    }
}
