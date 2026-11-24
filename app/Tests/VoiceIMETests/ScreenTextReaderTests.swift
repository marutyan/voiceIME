import CoreGraphics
import Foundation
import Vision
import XCTest
import os
@testable import VoiceIMECore

/// テスト用の小さなメモリ上 `CGImage` を生成する（ディスクへは一切書かない）。
func makeInMemoryTestCGImage(width: Int = 16, height: Int = 16) -> CGImage {
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let bitmapInfo = CGImageAlphaInfo.premultipliedLast.rawValue
    let context = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: colorSpace,
        bitmapInfo: bitmapInfo
    )!
    context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    return context.makeImage()!
}

/// テスト用に差し替え可能なウィンドウ撮影モック。
final class MockWindowImageCapturer: WindowImageCapturing, @unchecked Sendable {
    private struct State {
        var callCount: Int = 0
        var lastPreferredPid: pid_t?
    }

    private let state = OSAllocatedUnfairLock(initialState: State())
    private let delay: Duration
    private let imageProvider: @Sendable () throws -> CGImage?

    var callCount: Int { state.withLock { $0.callCount } }
    var lastPreferredPid: pid_t? { state.withLock { $0.lastPreferredPid } }

    init(
        delay: Duration = .zero,
        imageProvider: @escaping @Sendable () throws -> CGImage? = { makeInMemoryTestCGImage() }
    ) {
        self.delay = delay
        self.imageProvider = imageProvider
    }

    func captureFrontmostWindow(preferredPid: pid_t?) async throws -> CGImage? {
        state.withLock {
            $0.callCount += 1
            $0.lastPreferredPid = preferredPid
        }
        if delay > .zero {
            try await Task.sleep(for: delay)
        }
        return try imageProvider()
    }
}

/// テスト用に差し替え可能な文字認識モック。協調待機と非協調ブロッキングの両方を模擬できる。
final class MockImageTextRecognizer: ImageTextRecognizing, @unchecked Sendable {
    private let callCountLock = OSAllocatedUnfairLock(initialState: 0)
    private let delay: Duration
    private let blockingSleepSeconds: TimeInterval?
    private let linesProvider: @Sendable () throws -> [String]
    private let blockingQueue = DispatchQueue(label: "com.voiceime.tests.mock-ocr")

    var callCount: Int { callCountLock.withLock { $0 } }

    init(
        delay: Duration = .zero,
        blockingSleepSeconds: TimeInterval? = nil,
        linesProvider: @escaping @Sendable () throws -> [String]
    ) {
        self.delay = delay
        self.blockingSleepSeconds = blockingSleepSeconds
        self.linesProvider = linesProvider
    }

    func recognizeTextLines(in image: CGImage) async throws -> [String] {
        callCountLock.withLock { $0 += 1 }
        if let blockingSleepSeconds {
            let linesProvider = self.linesProvider
            return try await withCheckedThrowingContinuation { continuation in
                blockingQueue.async {
                    Thread.sleep(forTimeInterval: blockingSleepSeconds)
                    do {
                        continuation.resume(returning: try linesProvider())
                    } catch {
                        continuation.resume(throwing: error)
                    }
                }
            }
        }
        if delay > .zero {
            try await Task.sleep(for: delay)
        }
        return try linesProvider()
    }
}

/// 前面ウィンドウの文字整形・切り詰め・時間切れ・ウィンドウ選定・Vision設定を検証するテスト。
final class ScreenTextReaderTests: XCTestCase {
    private struct DummyError: Error {}

    func testFormatLinesJoinsNonEmptyLinesAndTruncatesTo4000Characters() {
        let formatted = EngineScreenText.format(lines: [
            "  PyTorch DataLoader  ",
            "",
            "   \t  ",
            "Hungarian Matching\n",
            "Qwen3.5-0.8B",
        ])
        XCTAssertEqual(formatted, "PyTorch DataLoader\nHungarian Matching\nQwen3.5-0.8B")

        let overLimit = EngineScreenText.format(lines: [
            String(repeating: "あ", count: 2_500),
            String(repeating: "い", count: 2_500),
        ])
        XCTAssertEqual(overLimit?.count, 4_000)
        XCTAssertTrue(overLimit?.hasPrefix(String(repeating: "あ", count: 2_500) + "\n") == true)
        XCTAssertEqual(
            overLimit,
            String(repeating: "あ", count: 2_500) + "\n" + String(repeating: "い", count: 1_499)
        )

        // ちょうど4,000字目が区切り改行になる境界では末尾の孤立改行を取り除くこと。
        let boundaryNewline = EngineScreenText.format(lines: [
            String(repeating: "a", count: 3_999),
            "b",
        ])
        XCTAssertEqual(boundaryNewline, String(repeating: "a", count: 3_999))

        XCTAssertNil(EngineScreenText.format(lines: []))
        XCTAssertNil(EngineScreenText.format(lines: ["", "   ", "\n\t"]))
    }

    func testReadFrontmostWindowTextReturnsFormattedTextWithinTimeout() async {
        let capturer = MockWindowImageCapturer(delay: .milliseconds(10))
        let recognizer = MockImageTextRecognizer(delay: .milliseconds(10)) {
            ["  PyTorch  ", "", "Hungarian Matching", "   "]
        }
        let reader = ScreenTextReader(capturer: capturer, recognizer: recognizer)

        let text = await reader.readFrontmostWindowText(
            preferredPid: 1234,
            timeout: .milliseconds(300)
        )

        XCTAssertEqual(text, "PyTorch\nHungarian Matching")
        XCTAssertEqual(capturer.callCount, 1)
        XCTAssertEqual(capturer.lastPreferredPid, 1234)
        XCTAssertEqual(recognizer.callCount, 1)
    }

    func testReadFrontmostWindowTextReturnsNilWhenRecognizedLinesAreEmpty() async {
        let capturer = MockWindowImageCapturer()
        let recognizer = MockImageTextRecognizer { ["", "  \n\t "] }
        let reader = ScreenTextReader(capturer: capturer, recognizer: recognizer)

        let text = await reader.readFrontmostWindowText(
            preferredPid: 42,
            timeout: .milliseconds(300)
        )

        XCTAssertNil(text)
        XCTAssertEqual(capturer.callCount, 1)
        XCTAssertEqual(recognizer.callCount, 1)
    }

    func testReadFrontmostWindowTextReturnsNilOnCaptureOrRecognitionFailure() async {
        let nilCapturer = MockWindowImageCapturer { nil }
        let recognizer = MockImageTextRecognizer { ["should not run"] }
        let nilReader = ScreenTextReader(capturer: nilCapturer, recognizer: recognizer)

        let nilResult = await nilReader.readFrontmostWindowText(
            preferredPid: 1,
            timeout: .milliseconds(300)
        )
        XCTAssertNil(nilResult)
        XCTAssertEqual(recognizer.callCount, 0)

        let failingCapturer = MockWindowImageCapturer { throw DummyError() }
        let captureFailReader = ScreenTextReader(capturer: failingCapturer, recognizer: recognizer)
        let captureFailResult = await captureFailReader.readFrontmostWindowText(
            preferredPid: 1,
            timeout: .milliseconds(300)
        )
        XCTAssertNil(captureFailResult)
        XCTAssertEqual(recognizer.callCount, 0)

        let okCapturer = MockWindowImageCapturer()
        let failingRecognizer = MockImageTextRecognizer { throw DummyError() }
        let ocrFailReader = ScreenTextReader(capturer: okCapturer, recognizer: failingRecognizer)
        let ocrFailResult = await ocrFailReader.readFrontmostWindowText(
            preferredPid: 1,
            timeout: .milliseconds(300)
        )
        XCTAssertNil(ocrFailResult)
        XCTAssertEqual(failingRecognizer.callCount, 1)
    }

    func testReadFrontmostWindowTextTimesOutWhenCaptureExceedsBudget() async {
        let capturer = MockWindowImageCapturer(delay: .seconds(2))
        let recognizer = MockImageTextRecognizer { ["遅すぎる結果"] }
        let reader = ScreenTextReader(capturer: capturer, recognizer: recognizer)

        let clock = ContinuousClock()
        let start = clock.now
        let text = await reader.readFrontmostWindowText(
            preferredPid: 100,
            timeout: .milliseconds(60)
        )
        let elapsed = clock.now - start

        XCTAssertNil(text)
        XCTAssertLessThan(elapsed, .milliseconds(400))
        XCTAssertEqual(recognizer.callCount, 0)
    }

    func testReadFrontmostWindowTextTimesOutPromptlyEvenWhenRecognitionIgnoresCancellation() async {
        let capturer = MockWindowImageCapturer()
        // Visionの同期処理のようにキャンセルに応答しない重いOCRを模擬する。
        let recognizer = MockImageTextRecognizer(blockingSleepSeconds: 0.5) {
            ["遅れて終わったOCR結果"]
        }
        let reader = ScreenTextReader(capturer: capturer, recognizer: recognizer)

        let clock = ContinuousClock()
        let start = clock.now
        let text = await reader.readFrontmostWindowText(
            preferredPid: 200,
            timeout: .milliseconds(50)
        )
        let elapsed = clock.now - start

        XCTAssertNil(text)
        XCTAssertLessThan(elapsed, .milliseconds(250))
    }

    func testSelectFrontmostWindowPrefersActiveSubstantialWindowOfPreferredPid() {
        let candidates = [
            // メニューバー等（layer != 0）は除外される。
            WindowCandidate(windowID: 1, owningPid: 50, windowLayer: 25, isOnScreen: true, isActive: true, frame: CGRect(x: 0, y: 0, width: 1200, height: 30)),
            // 自アプリ自身のウィンドウは除外される。
            WindowCandidate(windowID: 2, owningPid: 999, windowLayer: 0, isOnScreen: true, isActive: true, frame: CGRect(x: 0, y: 0, width: 800, height: 600)),
            // 前面アプリの1x1補助ウィンドウより通常サイズウィンドウを優先する。
            WindowCandidate(windowID: 3, owningPid: 50, windowLayer: 0, isOnScreen: true, isActive: true, frame: CGRect(x: 0, y: 0, width: 1, height: 1)),
            // 他アプリの前面ウィンドウ。
            WindowCandidate(windowID: 4, owningPid: 60, windowLayer: 0, isOnScreen: true, isActive: true, frame: CGRect(x: 0, y: 0, width: 1000, height: 700)),
            // 前面アプリの非アクティブウィンドウ。
            WindowCandidate(windowID: 5, owningPid: 50, windowLayer: 0, isOnScreen: true, isActive: false, frame: CGRect(x: 0, y: 0, width: 1000, height: 700)),
            // 前面アプリのアクティブな通常ウィンドウ（これを最優先で選ぶべき）。
            WindowCandidate(windowID: 6, owningPid: 50, windowLayer: 0, isOnScreen: true, isActive: true, frame: CGRect(x: 0, y: 0, width: 1280, height: 800)),
        ]

        let selected = ScreenCaptureKitWindowCapturer.selectFrontmostWindow(
            from: candidates,
            preferredPid: 50,
            ownPid: 999
        )
        XCTAssertEqual(selected?.windowID, 6)

        // preferredPid に該当ウィンドウが無い場合は他アプリの前面アクティブウィンドウへフォールバックする。
        let fallback = ScreenCaptureKitWindowCapturer.selectFrontmostWindow(
            from: candidates,
            preferredPid: 777,
            ownPid: 999
        )
        XCTAssertEqual(fallback?.windowID, 4)
    }

    func testCapturePixelSizeCapsLongestSideAt2048PreservingAspectRatio() {
        let small = ScreenCaptureKitWindowCapturer.capturePixelSize(
            contentRect: CGRect(x: 0, y: 0, width: 600, height: 400),
            pointPixelScale: 2.0
        )
        XCTAssertEqual(small.width, 1_200)
        XCTAssertEqual(small.height, 800)

        let retinaFull = ScreenCaptureKitWindowCapturer.capturePixelSize(
            contentRect: CGRect(x: 0, y: 0, width: 1_728, height: 1_117),
            pointPixelScale: 2.0
        )
        XCTAssertEqual(retinaFull.width, 2_048)
        XCTAssertEqual(retinaFull.height, 1_324)
    }

    func testVisionTextRecognizerRequestUsesJapaneseEnglishAndAccurateLevel() {
        let request = VisionTextRecognizer.makeRequest()
        XCTAssertEqual(request.recognitionLevel, .accurate)
        XCTAssertEqual(request.recognitionLanguages, ["ja-JP", "en-US"])
        XCTAssertTrue(request.usesLanguageCorrection)
    }
}
