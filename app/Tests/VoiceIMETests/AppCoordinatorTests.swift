import Foundation
import XCTest
import os
@testable import VoiceIMECore

/// テスト用の合成録音器。任意のタイミングでPCMサンプルを流し込める。
final class MockAudioRecorder: AudioRecorderProtocol, @unchecked Sendable {
    var isStarted = false
    var cancelCount = 0
    var stopTailSamples: [Int16] = []
    private var onSamples: (@Sendable ([Int16]) -> Void)?
    private var onError: (@Sendable (String) -> Void)?

    func start(
        onSamples: @escaping @Sendable ([Int16]) -> Void,
        onError: @escaping @Sendable (String) -> Void
    ) throws {
        self.onSamples = onSamples
        self.onError = onError
        self.isStarted = true
    }

    func feed(_ samples: [Int16]) {
        onSamples?(samples)
    }

    func stop() throws -> [Int16] {
        isStarted = false
        let tail = stopTailSamples
        stopTailSamples = []
        return tail
    }

    func cancel() {
        isStarted = false
        cancelCount += 1
    }
}

/// テスト用のホットキーモニター。
@MainActor
final class MockHotkeyMonitor: HotkeyMonitoring {
    var mode: HotkeyMode = .fnHold
    var isRecordingProvider: (() -> Bool)?
    var onAction: ((HotkeyAction) -> Void)?
    var startResult = true
    var startCount = 0
    var stopCount = 0

    func start() -> Bool {
        startCount += 1
        return startResult
    }

    func stop() {
        stopCount += 1
    }
}

/// テスト用の権限チェッカー。
struct MockPermissionChecker: PermissionChecking {
    let status: PermissionStatus

    func currentStatus() -> PermissionStatus {
        status
    }

    func requestMicrophonePermissionIfNeeded() async -> Bool {
        status.microphone
    }
}

/// 実行中に権限状態の変化や画面収録権限リクエスト回数を検証できるテスト用チェッカー。
final class MutableMockPermissionChecker: PermissionChecking, @unchecked Sendable {
    private struct State {
        var status: PermissionStatus
        var screenRecordingRequestCount: Int = 0
    }

    private let state: OSAllocatedUnfairLock<State>

    var status: PermissionStatus {
        get { state.withLock { $0.status } }
        set { state.withLock { $0.status = newValue } }
    }

    var screenRecordingRequestCount: Int {
        state.withLock { $0.screenRecordingRequestCount }
    }

    init(status: PermissionStatus) {
        self.state = OSAllocatedUnfairLock(initialState: State(status: status))
    }

    func currentStatus() -> PermissionStatus {
        state.withLock { $0.status }
    }

    func requestMicrophonePermissionIfNeeded() async -> Bool {
        state.withLock { $0.status.microphone }
    }

    func requestScreenRecordingPermission() -> Bool {
        state.withLock {
            $0.screenRecordingRequestCount += 1
            return $0.status.screenRecording
        }
    }
}

/// テスト用の通知記録器。
@MainActor
final class MockNotifier: UserNotifying {
    struct Entry: Equatable {
        let title: String
        let body: String
    }

    var entries: [Entry] = []

    func requestAuthorizationIfAvailable() {}

    func notify(title: String, body: String) {
        entries.append(Entry(title: title, body: body))
    }
}

/// ホットキー状態機械と、`AppCoordinator`全体の録音→分割→WAV送信→貼り付け→一時ファイル削除フローを検証するテスト。
@MainActor
final class AppCoordinatorTests: XCTestCase {
    private var tempDir: URL!

    override func setUp() async throws {
        try await super.setUp()
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("voiceime-coord-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        if let tempDir {
            try? FileManager.default.removeItem(at: tempDir)
        }
        try await super.tearDown()
    }

    private func makeEngineClient(
        behavior: String = "normal",
        logFile: URL? = nil
    ) throws -> EngineClient {
        guard let scriptURL = Bundle.module.url(
            forResource: "fake_engine",
            withExtension: "py",
            subdirectory: "Fixtures"
        ) else {
            throw NSError(domain: "AppCoordinatorTests", code: 1)
        }
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        env["FAKE_ENGINE_BEHAVIOR"] = behavior
        if let logFile {
            env["FAKE_ENGINE_LOG_FILE"] = logFile.path
        }
        let config = EngineLaunchConfig(
            executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
            arguments: ["-u", scriptURL.path],
            currentDirectoryURL: tempDir,
            environment: env
        )
        return EngineClient(launchConfig: config, restartBackoffSeconds: [0.05])
    }

    private func parseLoggedMessages(at logFile: URL) throws -> [[String: Any]] {
        guard FileManager.default.fileExists(atPath: logFile.path) else {
            return []
        }
        let lines = try String(contentsOf: logFile, encoding: .utf8)
            .split(separator: "\n")
            .map(String.init)
        return try lines.map { line in
            try XCTUnwrap(
                JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any]
            )
        }
    }

    // MARK: - HotkeyStateMachine Tests

    func testHotkeyStateMachineFnHoldAndEscapeCancel() {
        var sm = HotkeyStateMachine(mode: .fnHold)

        // fn + Command のような他修飾キー併用は録音開始しない。
        XCTAssertNil(sm.handle(.flagsChanged(flags: [.fn, .command]), isRecording: false).action)
        XCTAssertNil(sm.handle(.flagsChanged(flags: [.command]), isRecording: false).action)

        // 単体fn押下で開始、録音中のEscで取り消し、その後のfn解放では終了を送らない。
        XCTAssertEqual(sm.handle(.flagsChanged(flags: [.fn]), isRecording: false).action, .startRecording)
        let escTransition = sm.handle(.keyDown(keyCode: 53, flags: [.fn], isAutoRepeat: false), isRecording: true)
        XCTAssertEqual(escTransition.action, .cancelRecording)
        XCTAssertTrue(escTransition.shouldConsumeEvent)
        XCTAssertNil(sm.handle(.flagsChanged(flags: []), isRecording: false).action)

        // 次のfn押下〜解放は通常どおり開始・停止になる。
        XCTAssertEqual(sm.handle(.flagsChanged(flags: [.fn]), isRecording: false).action, .startRecording)
        XCTAssertEqual(sm.handle(.flagsChanged(flags: []), isRecording: true).action, .stopRecording)
    }

    func testHotkeyStateMachineControlOptionSpaceToggle() {
        var sm = HotkeyStateMachine(mode: .controlOptionSpaceToggle)

        // 余分な修飾キー（Command付き）やオートリピートは無視。
        XCTAssertNil(sm.handle(.keyDown(keyCode: 49, flags: [.control, .option, .command], isAutoRepeat: false), isRecording: false).action)
        XCTAssertNil(sm.handle(.keyDown(keyCode: 49, flags: [.control, .option], isAutoRepeat: true), isRecording: false).action)

        // Control + Option + Space でトグル発火＆イベント消費。
        let toggle = sm.handle(.keyDown(keyCode: 49, flags: [.control, .option], isAutoRepeat: false), isRecording: false)
        XCTAssertEqual(toggle.action, .toggleRecording)
        XCTAssertTrue(toggle.shouldConsumeEvent)

        // 待機中のEscは無視、録音中のEscは取り消し。
        XCTAssertNil(sm.handle(.keyDown(keyCode: 53, flags: [], isAutoRepeat: false), isRecording: false).action)
        XCTAssertEqual(sm.handle(.keyDown(keyCode: 53, flags: [], isAutoRepeat: false), isRecording: true).action, .cancelRecording)
    }

    // MARK: - End-to-End Coordinator Tests

    func testRecordingFlowWritesWavPastesResultAndDeletesTempWavAfterResult() async throws {
        let engine = try makeEngineClient(behavior: "normal")
        let recorder = MockAudioRecorder()
        let hotkey = MockHotkeyMonitor()
        let board = MockPasteboardClient(initialSnapshot: PasteboardSnapshot(items: [
            PasteboardItemSnapshot(entries: [PasteboardEntry(type: "public.utf8-plain-text", data: Data("元の値".utf8))]),
        ]))
        let target = PasteTarget(
            pid: 4242,
            bundleId: "com.apple.TextEdit",
            appName: "TextEdit",
            focusedElement: FocusedElementHandle("doc-1" as CFString)
        )
        let inputDriver = MockPasteInputDriver()
        var pastedText: String?
        inputDriver.onSendCommandV = {
            if let data = board.currentSnapshot.items.first?.entries.first(where: { $0.type == "public.utf8-plain-text" })?.data {
                pastedText = String(data: data, encoding: .utf8)
            }
        }
        let pasteController = PasteController(
            pasteboard: board,
            targetProvider: MockTargetProvider(target: target),
            inputDriver: inputDriver,
            restoreDelay: .milliseconds(5)
        )
        let notifier = MockNotifier()
        let wavDir = tempDir.appendingPathComponent("wavs", isDirectory: true)

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: hotkey,
            pasteController: pasteController,
            permissionChecker: MockPermissionChecker(status: PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)),
            notifier: notifier,
            tempDirectory: wavDir,
            userDefaults: nil,
            initialHotkeyMode: .fnHold,
            repastePreDelay: .zero
        )

        // ready前は録音開始が受け付けられないこと。
        coordinator.handleHotkeyAction(.startRecording)
        XCTAssertFalse(recorder.isStarted)

        let readyExp = expectation(description: "engine ready")
        let doneExp = expectation(description: "result pasted and returned idle")
        var becameReady = false
        var finishedFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !finishedFulfilled && state.iconState == .idle && state.lastResultText != nil {
                finishedFulfilled = true
                doneExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        // 録音開始 → 冒頭300ms無音 + 発話500ms + 無音600ms（1区間確定）+ 発話300ms → 録音終了
        coordinator.handleHotkeyAction(.startRecording)
        XCTAssertEqual(coordinator.uiState.iconState, .recording)
        XCTAssertTrue(recorder.isStarted)

        var pcm: [Int16] = []
        pcm.append(contentsOf: repeatElement(0, count: 15 * 320))    // 300ms校正
        pcm.append(contentsOf: repeatElement(4000, count: 25 * 320)) // 500ms発話1
        pcm.append(contentsOf: repeatElement(0, count: 30 * 320))    // 600ms無音 → seq 0確定
        pcm.append(contentsOf: repeatElement(4000, count: 15 * 320)) // 300ms発話2 → finishでseq 1確定
        recorder.feed(pcm)

        coordinator.handleHotkeyAction(.stopRecording)
        await fulfillment(of: [doneExp], timeout: 5.0)

        XCTAssertEqual(pastedText, "整形済み(0,1):wav_ok=true")
        XCTAssertEqual(coordinator.uiState.lastResultText, "整形済み(0,1):wav_ok=true")
        XCTAssertEqual(inputDriver.sendCommandVCallCount, 1)
        // 元のクリップボードが復元されていること。
        XCTAssertEqual(board.currentSnapshot.items.first?.entries.first?.data, Data("元の値".utf8))
        // 結果受信後に一時WAVファイルがすべて削除されていること。
        let remaining = (try? FileManager.default.contentsOfDirectory(atPath: wavDir.path)) ?? []
        XCTAssertTrue(remaining.isEmpty, "一時WAVが残っています: \(remaining)")

        await coordinator.stop()
    }

    func testEngineErrorWithRawTextPastesRawTextAndNotifies() async throws {
        let engine = try makeEngineClient(behavior: "error_with_raw")
        let recorder = MockAudioRecorder()
        let board = MockPasteboardClient()
        let target = PasteTarget(pid: 10, focusedElement: FocusedElementHandle("f" as CFString))
        let driver = MockPasteInputDriver()
        var pastedText: String?
        driver.onSendCommandV = {
            if let data = board.currentSnapshot.items.first?.entries.first(where: { $0.type == "public.utf8-plain-text" })?.data {
                pastedText = String(data: data, encoding: .utf8)
            }
        }
        let notifier = MockNotifier()

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: board,
                targetProvider: MockTargetProvider(target: target),
                inputDriver: driver,
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: MockPermissionChecker(status: PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)),
            notifier: notifier,
            tempDirectory: tempDir.appendingPathComponent("wavs-raw", isDirectory: true),
            userDefaults: nil,
            initialHotkeyMode: .fnHold
        )

        let readyExp = expectation(description: "ready")
        let finishedExp = expectation(description: "error handled")
        var becameReady = false
        var finishedFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !finishedFulfilled && state.iconState == .idle && state.lastResultText == "えーと 整形前の文" {
                finishedFulfilled = true
                finishedExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)

        await fulfillment(of: [finishedExp], timeout: 5.0)
        XCTAssertEqual(pastedText, "えーと 整形前の文")
        XCTAssertEqual(driver.sendCommandVCallCount, 1)
        XCTAssertTrue(notifier.entries.contains(where: { $0.body.contains("整形タイムアウト") }))

        await coordinator.stop()
    }

    func testMissingPermissionsTriggerGuidanceNotificationOnStart() async throws {
        let engine = try makeEngineClient(behavior: "normal")
        let notifier = MockNotifier()
        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: MockAudioRecorder(),
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: nil),
                inputDriver: MockPasteInputDriver()
            ),
            permissionChecker: MockPermissionChecker(
                status: PermissionStatus(microphone: false, accessibility: false, inputMonitoring: false)
            ),
            notifier: notifier,
            tempDirectory: tempDir.appendingPathComponent("wavs-perm", isDirectory: true),
            userDefaults: nil
        )

        coordinator.start()
        // 非同期の権限チェック完了を少し待つ。
        try await Task.sleep(for: .milliseconds(150))

        XCTAssertTrue(notifier.entries.contains(where: {
            $0.body.contains("マイク") && $0.body.contains("アクセシビリティ") && $0.body.contains("入力監視")
        }))

        await coordinator.stop()
    }

    func testEngineErrorWithoutRawTextDoesNotPasteAndNotifies() async throws {
        let engine = try makeEngineClient(behavior: "error_without_raw")
        let recorder = MockAudioRecorder()
        let board = MockPasteboardClient()
        let target = PasteTarget(pid: 20, focusedElement: FocusedElementHandle("f" as CFString))
        let driver = MockPasteInputDriver()
        let notifier = MockNotifier()

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: board,
                targetProvider: MockTargetProvider(target: target),
                inputDriver: driver,
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: MockPermissionChecker(status: PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)),
            notifier: notifier,
            tempDirectory: tempDir.appendingPathComponent("wavs-err", isDirectory: true),
            userDefaults: nil
        )

        let readyExp = expectation(description: "ready")
        let returnedIdleExp = expectation(description: "returned idle after error")
        var becameReady = false
        var enteredProcessing = false
        var finished = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && state.iconState == .processing {
                enteredProcessing = true
            } else if enteredProcessing && !finished && state.iconState == .idle {
                finished = true
                returnedIdleExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)

        await fulfillment(of: [returnedIdleExp], timeout: 5.0)
        XCTAssertEqual(driver.sendCommandVCallCount, 0)
        XCTAssertNil(coordinator.uiState.lastResultText)
        XCTAssertTrue(notifier.entries.contains(where: { $0.body.contains("認識に失敗しました") }))

        await coordinator.stop()
    }

    func testEscapeCancelDeletesTempWavsAndSendsCancel() async throws {
        let logFile = tempDir.appendingPathComponent("cancel-engine.log")
        guard let scriptURL = Bundle.module.url(
            forResource: "fake_engine",
            withExtension: "py",
            subdirectory: "Fixtures"
        ) else {
            XCTFail("fake_engine.py が見つかりません")
            return
        }
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        env["FAKE_ENGINE_LOG_FILE"] = logFile.path
        let engine = EngineClient(
            launchConfig: EngineLaunchConfig(
                executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
                arguments: ["-u", scriptURL.path],
                currentDirectoryURL: tempDir,
                environment: env
            ),
            restartBackoffSeconds: [0.05]
        )

        let recorder = MockAudioRecorder()
        let wavDir = tempDir.appendingPathComponent("wavs-cancel", isDirectory: true)
        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: PasteTarget(pid: 1)),
                inputDriver: MockPasteInputDriver()
            ),
            permissionChecker: MockPermissionChecker(status: PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)),
            notifier: MockNotifier(),
            tempDirectory: wavDir,
            userDefaults: nil
        )

        let readyExp = expectation(description: "ready")
        var becameReady = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        var pcm: [Int16] = []
        pcm.append(contentsOf: repeatElement(0, count: 15 * 320))    // 300ms校正
        pcm.append(contentsOf: repeatElement(4000, count: 20 * 320)) // 400ms発話
        pcm.append(contentsOf: repeatElement(0, count: 30 * 320))    // 600ms無音で1区間書き出し
        recorder.feed(pcm)
        try await Task.sleep(for: .milliseconds(50))

        coordinator.handleHotkeyAction(.cancelRecording)
        XCTAssertEqual(coordinator.uiState.iconState, .idle)
        XCTAssertEqual(recorder.cancelCount, 1)

        await coordinator.stop()

        let remaining = (try? FileManager.default.contentsOfDirectory(atPath: wavDir.path)) ?? []
        XCTAssertTrue(remaining.isEmpty, "取り消し後に一時WAVが残っています: \(remaining)")

        let logText = try String(contentsOf: logFile, encoding: .utf8)
        XCTAssertTrue(logText.contains("\"cancel\""))
        XCTAssertFalse(logText.contains("\"finish\""))
    }

    func testRepasteLastResultPastesEvenWhenTargetHasChanged() async throws {
        let engine = try makeEngineClient(behavior: "normal")
        let recorder = MockAudioRecorder()
        let board = MockPasteboardClient()
        let targetProvider = MockTargetProvider(
            target: PasteTarget(pid: 100, focusedElement: FocusedElementHandle("win-1" as CFString))
        )
        let driver = MockPasteInputDriver()
        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: board,
                targetProvider: targetProvider,
                inputDriver: driver,
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: MockPermissionChecker(status: PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)),
            notifier: MockNotifier(),
            tempDirectory: tempDir.appendingPathComponent("wavs-repaste", isDirectory: true),
            userDefaults: nil,
            repastePreDelay: .zero
        )

        let readyExp = expectation(description: "ready")
        let doneExp = expectation(description: "done")
        var becameReady = false
        var doneFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !doneFulfilled && state.iconState == .idle && state.lastResultText != nil {
                doneFulfilled = true
                doneExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)
        await fulfillment(of: [doneExp], timeout: 5.0)
        XCTAssertEqual(driver.sendCommandVCallCount, 1)

        // 別アプリへ切り替えた後でも「最後の結果をもう一度貼る」で貼れること。
        targetProvider.target = PasteTarget(pid: 999, focusedElement: FocusedElementHandle("other-app" as CFString))
        coordinator.repasteLastResult()
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertEqual(driver.sendCommandVCallCount, 2)

        await coordinator.stop()
    }

    // MARK: - Screen Text Context Tests

    func testRecordingSendsScreenTextInStartAndPreservesCommandOrder() async throws {
        let logFile = tempDir.appendingPathComponent("screen-ok.log")
        let engine = try makeEngineClient(behavior: "normal", logFile: logFile)
        let recorder = MockAudioRecorder()
        let board = MockPasteboardClient()
        let target = PasteTarget(
            pid: 5150,
            bundleId: "com.apple.dt.Xcode",
            appName: "Xcode",
            focusedElement: FocusedElementHandle("editor-1" as CFString)
        )
        let driver = MockPasteInputDriver()
        let capturer = MockWindowImageCapturer(delay: .milliseconds(25))
        let recognizer = MockImageTextRecognizer(delay: .milliseconds(25)) {
            ["  Qwen3.5-0.8B  ", "", "Hungarian Matching", "PyTorch DataLoader"]
        }
        let reader = ScreenTextReader(capturer: capturer, recognizer: recognizer)

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: board,
                targetProvider: MockTargetProvider(target: target),
                inputDriver: driver,
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: MockPermissionChecker(
                status: PermissionStatus(
                    microphone: true,
                    accessibility: true,
                    inputMonitoring: true,
                    screenRecording: true
                )
            ),
            notifier: MockNotifier(),
            screenTextReader: reader,
            tempDirectory: tempDir.appendingPathComponent("wavs-screen-ok", isDirectory: true),
            userDefaults: nil,
            screenTextTimeout: .milliseconds(300),
            repastePreDelay: .zero
        )

        XCTAssertTrue(coordinator.isScreenTextEnabled)
        XCTAssertEqual(coordinator.uiState.screenTextStatus, .enabled)
        XCTAssertEqual(coordinator.uiState.screenTextStatus.menuTitle, "画面の文字を使う（オン）")

        let readyExp = expectation(description: "ready")
        let doneExp = expectation(description: "done")
        var becameReady = false
        var doneFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !doneFulfilled && state.iconState == .idle && state.lastResultText != nil {
                doneFulfilled = true
                doneExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        // 録音開始はOCRの完了を待たず即座に開始されること。
        coordinator.handleHotkeyAction(.startRecording)
        XCTAssertTrue(recorder.isStarted)
        XCTAssertEqual(coordinator.uiState.iconState, .recording)

        // OCR実行中に音声が入り終了しても start -> segment -> finish の順序が保たれること。
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)

        await fulfillment(of: [doneExp], timeout: 5.0)
        XCTAssertEqual(coordinator.uiState.lastResultText, "整形済み(0):wav_ok=true")
        XCTAssertEqual(driver.sendCommandVCallCount, 1)
        XCTAssertEqual(capturer.lastPreferredPid, 5150)

        await coordinator.stop()

        let messages = try parseLoggedMessages(at: logFile)
        let types = messages.compactMap { $0["type"] as? String }
        XCTAssertEqual(types, ["start", "segment", "finish", "shutdown"])
        XCTAssertEqual(
            messages[0]["screen_text"] as? String,
            "Qwen3.5-0.8B\nHungarian Matching\nPyTorch DataLoader"
        )
    }

    func testRecordingTimesOutScreenTextAndSendsStartWithoutScreenText() async throws {
        let logFile = tempDir.appendingPathComponent("screen-timeout.log")
        let engine = try makeEngineClient(behavior: "normal", logFile: logFile)
        let recorder = MockAudioRecorder()
        let driver = MockPasteInputDriver()
        let target = PasteTarget(pid: 600, bundleId: "com.apple.Preview", appName: "Preview")

        let capturer = MockWindowImageCapturer()
        let recognizer = MockImageTextRecognizer(blockingSleepSeconds: 1.0) {
            ["遅すぎるOCR結果"]
        }
        let reader = ScreenTextReader(capturer: capturer, recognizer: recognizer)

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: target),
                inputDriver: driver,
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: MockPermissionChecker(
                status: PermissionStatus(
                    microphone: true,
                    accessibility: true,
                    inputMonitoring: true,
                    screenRecording: true
                )
            ),
            notifier: MockNotifier(),
            screenTextReader: reader,
            tempDirectory: tempDir.appendingPathComponent("wavs-screen-timeout", isDirectory: true),
            userDefaults: nil,
            screenTextTimeout: .milliseconds(60),
            repastePreDelay: .zero
        )

        let readyExp = expectation(description: "ready")
        let doneExp = expectation(description: "done")
        var becameReady = false
        var doneFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !doneFulfilled && state.iconState == .idle && state.lastResultText != nil {
                doneFulfilled = true
                doneExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        let clock = ContinuousClock()
        let startedAt = clock.now
        coordinator.handleHotkeyAction(.startRecording)
        XCTAssertTrue(recorder.isStarted)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)

        await fulfillment(of: [doneExp], timeout: 5.0)
        let elapsed = clock.now - startedAt
        // 1.0秒かかるOCRを待ち続けず、60msタイムアウト後に完了していること。
        XCTAssertLessThan(elapsed, .milliseconds(800))
        XCTAssertEqual(driver.sendCommandVCallCount, 1)

        await coordinator.stop()

        let messages = try parseLoggedMessages(at: logFile)
        let types = messages.compactMap { $0["type"] as? String }
        XCTAssertEqual(types, ["start", "segment", "finish", "shutdown"])
        XCTAssertFalse(messages[0].keys.contains("screen_text"))
    }

    func testRecordingOmitsScreenTextWhenOcrIsEmpty() async throws {
        let logFile = tempDir.appendingPathComponent("screen-empty.log")
        let engine = try makeEngineClient(behavior: "normal", logFile: logFile)
        let recorder = MockAudioRecorder()
        let reader = ScreenTextReader(
            capturer: MockWindowImageCapturer(),
            recognizer: MockImageTextRecognizer { ["  ", "\n"] }
        )

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: PasteTarget(pid: 700)),
                inputDriver: MockPasteInputDriver(),
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: MockPermissionChecker(
                status: PermissionStatus(
                    microphone: true,
                    accessibility: true,
                    inputMonitoring: true,
                    screenRecording: true
                )
            ),
            notifier: MockNotifier(),
            screenTextReader: reader,
            tempDirectory: tempDir.appendingPathComponent("wavs-screen-empty", isDirectory: true),
            userDefaults: nil,
            screenTextTimeout: .milliseconds(300),
            repastePreDelay: .zero
        )

        let readyExp = expectation(description: "ready")
        let doneExp = expectation(description: "done")
        var becameReady = false
        var doneFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !doneFulfilled && state.iconState == .idle && state.lastResultText != nil {
                doneFulfilled = true
                doneExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)
        await fulfillment(of: [doneExp], timeout: 5.0)

        await coordinator.stop()

        let messages = try parseLoggedMessages(at: logFile)
        let startMsg = try XCTUnwrap(messages.first)
        XCTAssertEqual(startMsg["type"] as? String, "start")
        XCTAssertFalse(startMsg.keys.contains("screen_text"))
    }

    func testMissingScreenRecordingPermissionContinuesWithoutScreenTextAndUpdatesMenuStatus() async throws {
        let logFile = tempDir.appendingPathComponent("screen-noperm.log")
        let engine = try makeEngineClient(behavior: "normal", logFile: logFile)
        let recorder = MockAudioRecorder()
        let notifier = MockNotifier()
        let capturer = MockWindowImageCapturer()
        let reader = ScreenTextReader(
            capturer: capturer,
            recognizer: MockImageTextRecognizer { ["読まれないはず"] }
        )
        let permissions = MutableMockPermissionChecker(
            status: PermissionStatus(
                microphone: true,
                accessibility: true,
                inputMonitoring: true,
                screenRecording: false
            )
        )

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: PasteTarget(pid: 800)),
                inputDriver: MockPasteInputDriver(),
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: permissions,
            notifier: notifier,
            screenTextReader: reader,
            tempDirectory: tempDir.appendingPathComponent("wavs-screen-noperm", isDirectory: true),
            userDefaults: nil,
            repastePreDelay: .zero
        )

        // 既定はオンだが権限が無いため「権限なし」になること。
        XCTAssertTrue(coordinator.isScreenTextEnabled)
        XCTAssertEqual(coordinator.uiState.screenTextStatus, .permissionMissing)
        XCTAssertEqual(coordinator.uiState.screenTextStatus.menuTitle, "画面の文字を使う（権限なし）")

        let readyExp = expectation(description: "ready")
        let doneExp = expectation(description: "done")
        var becameReady = false
        var doneFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !doneFulfilled && state.iconState == .idle && state.lastResultText != nil {
                doneFulfilled = true
                doneExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)
        await fulfillment(of: [doneExp], timeout: 5.0)

        // 権限なしでも録音・貼り付けは継続し、画面撮影は実行されず screen_text 欄も出ない。
        XCTAssertEqual(capturer.callCount, 0)
        XCTAssertEqual(coordinator.uiState.lastResultText, "整形済み(0):wav_ok=true")

        // 権限要求メニューを実行するとチェッカーへ委譲され案内通知が出る。
        coordinator.requestScreenRecordingPermission()
        XCTAssertEqual(permissions.screenRecordingRequestCount, 1)
        XCTAssertTrue(notifier.entries.contains(where: { $0.body.contains("画面収録") }))

        // 権限が付与された後に再確認すると「オン」へ遷移する。
        permissions.status = PermissionStatus(
            microphone: true,
            accessibility: true,
            inputMonitoring: true,
            screenRecording: true
        )
        coordinator.refreshScreenRecordingPermission()
        XCTAssertEqual(coordinator.uiState.screenTextStatus, .enabled)
        XCTAssertEqual(coordinator.uiState.screenTextStatus.menuTitle, "画面の文字を使う（オン）")

        await coordinator.stop()

        let messages = try parseLoggedMessages(at: logFile)
        let startMsg = try XCTUnwrap(messages.first)
        XCTAssertEqual(startMsg["type"] as? String, "start")
        XCTAssertFalse(startMsg.keys.contains("screen_text"))
    }

    func testScreenTextMenuTogglePersistsToUserDefaultsAndSkipsCaptureWhenDisabled() async throws {
        let suiteName = "com.voiceime.tests.screen-toggle.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let logFile = tempDir.appendingPathComponent("screen-disabled.log")
        let engine = try makeEngineClient(behavior: "normal", logFile: logFile)
        let recorder = MockAudioRecorder()
        let capturer = MockWindowImageCapturer()
        let reader = ScreenTextReader(
            capturer: capturer,
            recognizer: MockImageTextRecognizer { ["オフなので読まれない"] }
        )
        let permissions = MockPermissionChecker(
            status: PermissionStatus(
                microphone: true,
                accessibility: true,
                inputMonitoring: true,
                screenRecording: true
            )
        )

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: PasteTarget(pid: 900)),
                inputDriver: MockPasteInputDriver(),
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: permissions,
            notifier: MockNotifier(),
            screenTextReader: reader,
            tempDirectory: tempDir.appendingPathComponent("wavs-screen-off", isDirectory: true),
            userDefaults: defaults,
            repastePreDelay: .zero
        )

        XCTAssertTrue(coordinator.isScreenTextEnabled)
        XCTAssertEqual(coordinator.uiState.screenTextStatus, .enabled)

        coordinator.toggleScreenTextEnabled()
        XCTAssertFalse(coordinator.isScreenTextEnabled)
        XCTAssertEqual(coordinator.uiState.screenTextStatus, .disabled)
        XCTAssertEqual(coordinator.uiState.screenTextStatus.menuTitle, "画面の文字を使う（オフ）")

        let readyExp = expectation(description: "ready")
        let doneExp = expectation(description: "done")
        var becameReady = false
        var doneFulfilled = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !doneFulfilled && state.iconState == .idle && state.lastResultText != nil {
                doneFulfilled = true
                doneExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        coordinator.handleHotkeyAction(.stopRecording)
        await fulfillment(of: [doneExp], timeout: 5.0)

        XCTAssertEqual(capturer.callCount, 0)
        await coordinator.stop()

        let messages = try parseLoggedMessages(at: logFile)
        XCTAssertEqual(messages.first?["type"] as? String, "start")
        XCTAssertFalse(messages.first?.keys.contains("screen_text") == true)

        // 再起動相当で同じ UserDefaults から生成した場合、オフ設定が引き継がれること。
        let restored = AppCoordinator(
            engineClient: try makeEngineClient(behavior: "normal"),
            audioRecorder: MockAudioRecorder(),
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: nil),
                inputDriver: MockPasteInputDriver()
            ),
            permissionChecker: permissions,
            notifier: MockNotifier(),
            screenTextReader: reader,
            tempDirectory: tempDir.appendingPathComponent("wavs-screen-restored", isDirectory: true),
            userDefaults: defaults
        )
        XCTAssertFalse(restored.isScreenTextEnabled)
        XCTAssertEqual(restored.uiState.screenTextStatus, .disabled)

        restored.toggleScreenTextEnabled()
        XCTAssertTrue(restored.isScreenTextEnabled)
        XCTAssertEqual(restored.uiState.screenTextStatus, .enabled)
    }

    func testEscapeCancelWhileScreenTextIsPendingDoesNotSendStartOrFinish() async throws {
        let logFile = tempDir.appendingPathComponent("screen-cancel.log")
        let engine = try makeEngineClient(behavior: "normal", logFile: logFile)
        let recorder = MockAudioRecorder()
        let wavDir = tempDir.appendingPathComponent("wavs-screen-cancel", isDirectory: true)
        let reader = ScreenTextReader(
            capturer: MockWindowImageCapturer(delay: .seconds(2)),
            recognizer: MockImageTextRecognizer { ["キャンセルされるので送られない"] }
        )

        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: PasteTarget(pid: 950)),
                inputDriver: MockPasteInputDriver()
            ),
            permissionChecker: MockPermissionChecker(
                status: PermissionStatus(
                    microphone: true,
                    accessibility: true,
                    inputMonitoring: true,
                    screenRecording: true
                )
            ),
            notifier: MockNotifier(),
            screenTextReader: reader,
            tempDirectory: wavDir,
            userDefaults: nil,
            screenTextTimeout: .milliseconds(300)
        )

        let readyExp = expectation(description: "ready")
        var becameReady = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        coordinator.handleHotkeyAction(.startRecording)
        try await Task.sleep(for: .milliseconds(20))
        coordinator.handleHotkeyAction(.cancelRecording)

        XCTAssertEqual(coordinator.uiState.iconState, .idle)
        XCTAssertEqual(recorder.cancelCount, 1)

        // 元のタイムアウト時間を超えても、取り消したセッションの start は送られないこと。
        try await Task.sleep(for: .milliseconds(100))
        await coordinator.stop()

        let messages = try parseLoggedMessages(at: logFile)
        let types = messages.compactMap { $0["type"] as? String }
        XCTAssertFalse(types.contains("start"))
        XCTAssertFalse(types.contains("finish"))
    }

    // MARK: - Overlay State & Layout Tests

    func testOverlayMetricsAndThemeColorsMatchMockSpec() {
        // 試作 docs/ui-mock/overlay.html（案A .pill-a）の固定実寸値を具体的な数値で守る。
        XCTAssertEqual(OverlayMetrics.cornerRadius, 16)
        XCTAssertEqual(OverlayMetrics.borderWidth, 1)
        XCTAssertEqual(OverlayMetrics.topHighlightHeight, 0.5)
        XCTAssertEqual(OverlayMetrics.compactRecordingSize, CGSize(width: 124, height: 32))
        XCTAssertEqual(OverlayMetrics.partialRecordingWidth, 300)
        XCTAssertEqual(OverlayMetrics.partialRecordingMinHeight, 60)
        XCTAssertEqual(OverlayMetrics.processingSize, CGSize(width: 112, height: 32))
        XCTAssertEqual(OverlayMetrics.doneSize, CGSize(width: 32, height: 32))
        XCTAssertEqual(OverlayMetrics.errorHeight, 32)
        XCTAssertEqual(OverlayMetrics.errorMaxWidth, 248)
        XCTAssertEqual(OverlayMetrics.recDotSize, 8)
        XCTAssertEqual(OverlayMetrics.waveBarCount, 9)
        XCTAssertEqual(OverlayMetrics.waveBarWidth, 2)
        XCTAssertEqual(OverlayMetrics.waveBarGap, 3)
        XCTAssertEqual(OverlayMetrics.waveBarMinHeight, 4)
        XCTAssertEqual(OverlayMetrics.waveBarMaxHeight, 16)
        XCTAssertEqual(OverlayMetrics.spinnerSize, 14)
        XCTAssertEqual(OverlayMetrics.checkIconSize, 16)
        XCTAssertEqual(OverlayMetrics.errorIconSize, 14)
        XCTAssertEqual(OverlayMetrics.bottomMarginAboveDock, 14)
        XCTAssertEqual(OverlayMetrics.doneAutoHideDelay, .milliseconds(880))
        XCTAssertEqual(OverlayMetrics.processingText, "整形中…")
        XCTAssertEqual(OverlayMetrics.menuTitle(isEnabled: true), "録音中の表示（オン）")
        XCTAssertEqual(OverlayMetrics.menuTitle(isEnabled: false), "録音中の表示（オフ）")

        // ライト／ダーク配色トークン（試作 CSS 値そのまま）。
        XCTAssertEqual(OverlayThemePalette.light.hudBackground, OverlayRGBAColor(r255: 250, g255: 250, b255: 252, alpha: 0.86))
        XCTAssertEqual(OverlayThemePalette.light.sysRed, OverlayRGBAColor(r255: 255, g255: 59, b255: 48, alpha: 1.0))
        XCTAssertEqual(OverlayThemePalette.light.sysRedText, OverlayRGBAColor(r255: 200, g255: 30, b255: 23, alpha: 1.0))
        XCTAssertEqual(OverlayThemePalette.light.sysGreen, OverlayRGBAColor(r255: 40, g255: 205, b255: 65, alpha: 1.0))
        XCTAssertEqual(OverlayThemePalette.light.primaryShadow, OverlayShadowSpec(offsetY: 8, blurRadius: 24, alpha: 0.13))

        XCTAssertEqual(OverlayThemePalette.dark.hudBackground, OverlayRGBAColor(r255: 38, g255: 38, b255: 43, alpha: 0.86))
        XCTAssertEqual(OverlayThemePalette.dark.sysRed, OverlayRGBAColor(r255: 255, g255: 69, b255: 58, alpha: 1.0))
        XCTAssertEqual(OverlayThemePalette.dark.sysRedText, OverlayRGBAColor(r255: 255, g255: 105, b255: 97, alpha: 1.0))
        XCTAssertEqual(OverlayThemePalette.dark.sysGreen, OverlayRGBAColor(r255: 48, g255: 209, b255: 88, alpha: 1.0))
        XCTAssertEqual(OverlayThemePalette.dark.primaryShadow, OverlayShadowSpec(offsetY: 12, blurRadius: 30, alpha: 0.50))
    }

    func testOverlayPanelLayoutAnchorsBottomCenterAboveDockAndExpandsUpward() {
        let visibleFrame = CGRect(x: 0, y: 70, width: 1440, height: 805)
        let canvasSize = CGSize(width: 396, height: 176)
        let bottomInset: CGFloat = 56

        let panelFrame = OverlayPanelLayout.panelFrame(
            canvasSize: canvasSize,
            bottomInset: bottomInset,
            in: visibleFrame
        )
        XCTAssertEqual(panelFrame, CGRect(x: 522, y: 28, width: 396, height: 176))
        // ピル下端（panelFrame.minY + bottomInset）が Dock 上端(70) + 14pt = 84pt に一致すること。
        XCTAssertEqual(panelFrame.minY + bottomInset, 84)

        let compactFrame = OverlayPanelLayout.pillFrameInCanvas(
            pillSize: CGSize(width: 124, height: 32),
            canvasSize: canvasSize,
            bottomInset: bottomInset
        )
        let partialOneLine = OverlayPanelLayout.partialPillSize(measuredTextHeight: 17)
        let partialTwoLines = OverlayPanelLayout.partialPillSize(measuredTextHeight: 34)
        let partialOverflow = OverlayPanelLayout.partialPillSize(measuredTextHeight: 72)

        XCTAssertEqual(partialOneLine, CGSize(width: 300, height: 60))
        XCTAssertEqual(partialTwoLines, CGSize(width: 300, height: 77))
        // 3行以上でも最大2行の高さへ抑えられること。
        XCTAssertEqual(partialOverflow, CGSize(width: 300, height: 77))

        let expandedFrame = OverlayPanelLayout.pillFrameInCanvas(
            pillSize: partialTwoLines,
            canvasSize: canvasSize,
            bottomInset: bottomInset
        )
        // 展開時に下端（minY）は固定されたまま上方向（maxY）へ広がること。
        XCTAssertEqual(compactFrame.minY, 56)
        XCTAssertEqual(expandedFrame.minY, 56)
        XCTAssertEqual(compactFrame.maxY, 88)
        XCTAssertEqual(expandedFrame.maxY, 133)
        XCTAssertEqual(compactFrame.midX, 198)
        XCTAssertEqual(expandedFrame.midX, 198)

        XCTAssertEqual(OverlayPanelLayout.errorPillSize(measuredTextWidth: 80), CGSize(width: 124, height: 32))
        XCTAssertEqual(OverlayPanelLayout.errorPillSize(measuredTextWidth: 300), CGSize(width: 248, height: 32))
    }

    func testOverlayPanelLayoutSelectsFrontmostScreenAcrossDisplays() {
        let screens = [
            OverlayPanelLayout.ScreenGeometry(
                frame: CGRect(x: 0, y: 0, width: 1440, height: 900),
                visibleFrame: CGRect(x: 0, y: 70, width: 1440, height: 805)
            ),
            OverlayPanelLayout.ScreenGeometry(
                frame: CGRect(x: 1440, y: 0, width: 1920, height: 1080),
                visibleFrame: CGRect(x: 1440, y: 0, width: 1920, height: 1055)
            ),
        ]

        // サブディスプレイ上にある前面ウィンドウ（CG座標）から index 1 が選ばれること。
        let subWindowCG = CGRect(x: 1600, y: 100, width: 800, height: 600)
        XCTAssertEqual(
            OverlayPanelLayout.selectScreenIndex(
                screens: screens,
                frontmostWindowCGFrame: subWindowCG,
                mainScreenIndex: 0,
                mouseLocation: CGPoint(x: 100, y: 100)
            ),
            1
        )
        // 前面ウィンドウ不明時は mainScreenIndex → mouseLocation → 0 の順でフォールバックすること。
        XCTAssertEqual(
            OverlayPanelLayout.selectScreenIndex(
                screens: screens,
                frontmostWindowCGFrame: nil,
                mainScreenIndex: 1,
                mouseLocation: CGPoint(x: 100, y: 100)
            ),
            1
        )
        XCTAssertEqual(
            OverlayPanelLayout.selectScreenIndex(
                screens: screens,
                frontmostWindowCGFrame: nil,
                mainScreenIndex: nil,
                mouseLocation: CGPoint(x: 1800, y: 300)
            ),
            1
        )
        XCTAssertEqual(
            OverlayPanelLayout.selectScreenIndex(
                screens: screens,
                frontmostWindowCGFrame: nil,
                mainScreenIndex: nil,
                mouseLocation: nil
            ),
            0
        )
    }

    func testOverlayAudioLevelAndWaveformBarHeights() {
        let silentLevel = OverlayAudioLevel.normalizedLevel(from: [Int16](repeating: 0, count: 320))
        XCTAssertEqual(silentLevel, 0, accuracy: 0.0001)
        let silentBars = OverlayAudioLevel.barHeights(envelope: 0, timeSeconds: 1.0)
        XCTAssertEqual(silentBars.count, 9)
        XCTAssertEqual(silentBars, [4, 4, 4, 4, 4, 4, 4, 4, 4])

        let speechLevel = OverlayAudioLevel.normalizedLevel(from: [Int16](repeating: 4000, count: 320))
        XCTAssertGreaterThan(speechLevel, 0.7)
        XCTAssertLessThan(speechLevel, 0.85)
        let speechBars = OverlayAudioLevel.barHeights(envelope: Double(speechLevel), timeSeconds: 0.0)
        XCTAssertEqual(speechBars.count, 9)
        for height in speechBars {
            XCTAssertGreaterThanOrEqual(height, 4.0)
            XCTAssertLessThanOrEqual(height, 16.0)
        }
        XCTAssertGreaterThan(speechBars[4], speechBars[0])

        XCTAssertEqual(OverlayAudioLevel.formatElapsed(seconds: -5), "0:00")
        XCTAssertEqual(OverlayAudioLevel.formatElapsed(seconds: 0), "0:00")
        XCTAssertEqual(OverlayAudioLevel.formatElapsed(seconds: 4), "0:04")
        XCTAssertEqual(OverlayAudioLevel.formatElapsed(seconds: 65), "1:05")
    }

    func testOverlayPanelConfigurationPreservesFocusAndMousePassthrough() {
        XCTAssertTrue(OverlayPanel.requiredStyleMask.contains(.nonactivatingPanel))
        XCTAssertTrue(OverlayPanel.requiredStyleMask.contains(.borderless))
        XCTAssertTrue(OverlayPanel.requiredCollectionBehavior.contains(.canJoinAllSpaces))
        XCTAssertTrue(OverlayPanel.requiredCollectionBehavior.contains(.fullScreenAuxiliary))

        let panel = OverlayPanel(contentRect: CGRect(x: 0, y: 0, width: 396, height: 176))
        XCTAssertTrue(panel.styleMask.contains(.nonactivatingPanel))
        XCTAssertFalse(panel.canBecomeKey)
        XCTAssertFalse(panel.canBecomeMain)
        XCTAssertTrue(panel.ignoresMouseEvents)
        XCTAssertEqual(panel.level, .floating)
        XCTAssertTrue(panel.collectionBehavior.contains(.canJoinAllSpaces))
        XCTAssertTrue(panel.collectionBehavior.contains(.fullScreenAuxiliary))
        XCTAssertFalse(panel.hidesOnDeactivate)
    }

    func testOverlayStateMachineTransitionsPartialDoneErrorAndToggle() {
        var sm = OverlayStateMachine(isEnabled: true)
        XCTAssertEqual(sm.displayState, .hidden)

        // 録音開始 → コンパクト録音状態。
        let startTransition = sm.apply(.recordingStarted)
        XCTAssertEqual(startTransition.displayState, .recording(OverlayRecordingState()))
        XCTAssertTrue(startTransition.shouldCancelAutoHide)

        // 空白だけの partial は展開しない。
        sm.apply(.partialReceived(seq: 0, text: "  \n "))
        XCTAssertEqual(sm.displayState, .recording(OverlayRecordingState()))

        // seq 0 → seq 1 の順に partial を受けると prefix / latest へ分かれて展開する。
        sm.apply(.partialReceived(seq: 0, text: "PyTorchのDataLoaderで"))
        XCTAssertEqual(
            sm.displayState,
            .recording(OverlayRecordingState(partialPrefix: "", partialLatest: "PyTorchのDataLoaderで", partialRevision: 1))
        )
        sm.apply(.partialReceived(seq: 1, text: "pin_memoryを\n有効にして"))
        XCTAssertEqual(
            sm.displayState,
            .recording(
                OverlayRecordingState(
                    partialPrefix: "PyTorchのDataLoaderで ",
                    partialLatest: "pin_memoryを 有効にして",
                    partialRevision: 2
                )
            )
        )

        // 処理中へ遷移後は遅れて到着した partial を無視する。
        sm.apply(.processingStarted)
        XCTAssertEqual(sm.displayState, .processing)
        sm.apply(.partialReceived(seq: 2, text: "遅れた途中結果"))
        XCTAssertEqual(sm.displayState, .processing)

        // 貼り付け成功 → 完了チェック＋自動消去スケジュール。
        let doneTransition = sm.apply(.pasteSucceeded)
        XCTAssertEqual(doneTransition.displayState, .done)
        guard case let .done(doneToken) = doneTransition.autoHideSchedule else {
            XCTFail("完了の自動消去スケジュールが発行されていません")
            return
        }
        // 古いトークンでは消えず、一致するトークンで非表示になる。
        sm.apply(.autoHideTimerFired(token: doneToken &- 1))
        XCTAssertEqual(sm.displayState, .done)
        sm.apply(.autoHideTimerFired(token: doneToken))
        XCTAssertEqual(sm.displayState, .hidden)

        // 完了表示中に次の録音が即座に始まればタイマーはキャンセルされる。
        let secondDone = sm.apply(.pasteSucceeded)
        guard case let .done(secondToken) = secondDone.autoHideSchedule else {
            XCTFail("2回目の完了スケジュールがありません")
            return
        }
        let nextRec = sm.apply(.recordingStarted)
        XCTAssertTrue(nextRec.shouldCancelAutoHide)
        XCTAssertEqual(nextRec.displayState, .recording(OverlayRecordingState()))
        sm.apply(.autoHideTimerFired(token: secondToken))
        XCTAssertEqual(sm.displayState, .recording(OverlayRecordingState()))

        // 表示オフ時は常に .hidden となり、オンへ戻すと進行中状態が復元される。
        sm.apply(.setEnabled(false))
        XCTAssertEqual(sm.displayState, .hidden)
        sm.apply(.setEnabled(true))
        XCTAssertEqual(sm.displayState, .recording(OverlayRecordingState()))

        // 入力先変更フォールバックは短いエラー文言になり、engineReady では消えない。
        sm.apply(.pasteFallback(.targetChanged))
        XCTAssertEqual(sm.displayState, .error(message: "入力先変更：コピーしました"))
        sm.apply(.engineReady)
        XCTAssertEqual(sm.displayState, .error(message: "入力先変更：コピーしました"))

        // エンジン接続エラーは engineReady で自動解除される。
        sm.apply(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
        XCTAssertEqual(sm.displayState, .error(message: "認識エンジンに接続できません"))
        sm.apply(.engineReady)
        XCTAssertEqual(sm.displayState, .hidden)
    }

    func testCoordinatorOverlayLifecyclePartialAudioLevelAndDoneAutoHide() async throws {
        let engine = try makeEngineClient(behavior: "normal")
        let recorder = MockAudioRecorder()
        let target = PasteTarget(pid: 3100, bundleId: "com.apple.TextEdit", appName: "TextEdit")
        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: target),
                inputDriver: MockPasteInputDriver(),
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: MockPermissionChecker(
                status: PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)
            ),
            notifier: MockNotifier(),
            tempDirectory: tempDir.appendingPathComponent("wavs-overlay-flow", isDirectory: true),
            userDefaults: nil,
            repastePreDelay: .zero,
            doneAutoHideDelay: .milliseconds(80),
            errorAutoHideDelay: .milliseconds(80)
        )

        var audioLevels: [Float] = []
        coordinator.onAudioLevelChange = { level in
            audioLevels.append(level)
        }

        let readyExp = expectation(description: "ready")
        let partialExp = expectation(description: "partial received")
        let doneVisibleExp = expectation(description: "done overlay visible")
        let doneHiddenExp = expectation(description: "done overlay auto-hidden")
        var becameReady = false
        var sawPartial = false
        var sawProcessing = false
        var sawDone = false
        var hidAfterDone = false

        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !sawPartial,
                      case let .recording(rec) = state.overlayState,
                      rec.partialLatest == "区間0" {
                sawPartial = true
                partialExp.fulfill()
            } else if sawPartial && state.overlayState == .processing {
                sawProcessing = true
            } else if sawProcessing && !sawDone && state.overlayState == .done {
                sawDone = true
                doneVisibleExp.fulfill()
            } else if sawDone && !hidAfterDone && state.overlayState == .hidden {
                hidAfterDone = true
                doneHiddenExp.fulfill()
            }
        }

        XCTAssertEqual(coordinator.uiState.overlayState, .hidden)
        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)
        XCTAssertEqual(coordinator.uiState.overlayState, .hidden)

        // 録音開始 → コンパクト録音表示。
        coordinator.handleHotkeyAction(.startRecording)
        XCTAssertEqual(coordinator.uiState.overlayState, .recording(OverlayRecordingState()))

        // 発話＋無音600ms で区間0が確定し、音量レベル通知と partial 展開が起きること。
        var pcm: [Int16] = []
        pcm.append(contentsOf: repeatElement(0, count: 15 * 320))
        pcm.append(contentsOf: repeatElement(4000, count: 25 * 320))
        pcm.append(contentsOf: repeatElement(0, count: 30 * 320))
        recorder.feed(pcm)
        await fulfillment(of: [partialExp], timeout: 5.0)
        XCTAssertTrue(audioLevels.contains(where: { $0 > 0.5 }))

        // 録音終了 → 処理中 → 完了チェック → 約0.9秒相当（テストでは80ms）で自動消去。
        coordinator.handleHotkeyAction(.stopRecording)
        await fulfillment(of: [doneVisibleExp, doneHiddenExp], timeout: 5.0)
        XCTAssertEqual(coordinator.uiState.overlayState, .hidden)

        await coordinator.stop()
    }

    func testCoordinatorOverlayShowsErrorOnMissingMicAndTargetChangedFallback() async throws {
        let engine = try makeEngineClient(behavior: "normal")
        let recorder = MockAudioRecorder()
        let permissions = MutableMockPermissionChecker(
            status: PermissionStatus(microphone: false, accessibility: true, inputMonitoring: true)
        )
        let targetProvider = MockTargetProvider(
            target: PasteTarget(pid: 4001, focusedElement: FocusedElementHandle("doc-a" as CFString))
        )
        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: targetProvider,
                inputDriver: MockPasteInputDriver(),
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: permissions,
            notifier: MockNotifier(),
            tempDirectory: tempDir.appendingPathComponent("wavs-overlay-err", isDirectory: true),
            userDefaults: nil,
            repastePreDelay: .zero,
            doneAutoHideDelay: .milliseconds(60),
            errorAutoHideDelay: .milliseconds(80)
        )

        let readyExp = expectation(description: "ready")
        let targetErrExp = expectation(description: "target changed overlay error")
        var becameReady = false
        var sawTargetErr = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            } else if becameReady && !sawTargetErr && state.overlayState == .error(message: "入力先変更：コピーしました") {
                sawTargetErr = true
                targetErrExp.fulfill()
            }
        }

        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        // マイク権限なしで録音開始 → エラーピル表示後に自動消去。
        coordinator.handleHotkeyAction(.startRecording)
        XCTAssertEqual(coordinator.uiState.overlayState, .error(message: "マイク権限がありません"))
        try await Task.sleep(for: .milliseconds(150))
        XCTAssertEqual(coordinator.uiState.overlayState, .hidden)

        // マイク権限ありで録音後、宛先変更でコピーフォールバック → エラーピル表示。
        permissions.status = PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)
        coordinator.handleHotkeyAction(.startRecording)
        recorder.feed([Int16](repeating: 4000, count: 20 * 320))
        targetProvider.target = PasteTarget(pid: 9999, focusedElement: FocusedElementHandle("doc-b" as CFString))
        coordinator.handleHotkeyAction(.stopRecording)
        await fulfillment(of: [targetErrExp], timeout: 5.0)

        await coordinator.stop()
    }

    func testOverlayMenuTogglePersistsToUserDefaultsAndHidesWhileDisabled() async throws {
        let suiteName = "com.voiceime.tests.overlay-toggle.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let engine = try makeEngineClient(behavior: "normal")
        let recorder = MockAudioRecorder()
        let permissions = MockPermissionChecker(
            status: PermissionStatus(microphone: true, accessibility: true, inputMonitoring: true)
        )
        let coordinator = AppCoordinator(
            engineClient: engine,
            audioRecorder: recorder,
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: PasteTarget(pid: 5000)),
                inputDriver: MockPasteInputDriver(),
                restoreDelay: .milliseconds(5)
            ),
            permissionChecker: permissions,
            notifier: MockNotifier(),
            tempDirectory: tempDir.appendingPathComponent("wavs-overlay-pref", isDirectory: true),
            userDefaults: defaults,
            repastePreDelay: .zero
        )

        // 既定はオン。
        XCTAssertTrue(coordinator.isOverlayEnabled)
        XCTAssertTrue(coordinator.uiState.isOverlayEnabled)

        let readyExp = expectation(description: "ready")
        var becameReady = false
        coordinator.onUIStateChange = { state in
            if !becameReady && state.iconState == .idle {
                becameReady = true
                readyExp.fulfill()
            }
        }
        coordinator.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        // オフに切り替えると録音中でもオーバーレイは非表示のまま。
        coordinator.toggleOverlayEnabled()
        XCTAssertFalse(coordinator.isOverlayEnabled)
        XCTAssertFalse(coordinator.uiState.isOverlayEnabled)

        coordinator.handleHotkeyAction(.startRecording)
        XCTAssertEqual(coordinator.uiState.iconState, .recording)
        XCTAssertEqual(coordinator.uiState.overlayState, .hidden)

        // 録音中にオンへ戻すと即座に録音表示へ切り替わる。
        coordinator.toggleOverlayEnabled()
        XCTAssertEqual(coordinator.uiState.overlayState, .recording(OverlayRecordingState()))
        coordinator.handleHotkeyAction(.cancelRecording)
        XCTAssertEqual(coordinator.uiState.overlayState, .hidden)

        // 再びオフにして終了し、再起動相当で同じ UserDefaults から復元されること。
        coordinator.setOverlayEnabled(false)
        await coordinator.stop()

        let restored = AppCoordinator(
            engineClient: try makeEngineClient(behavior: "normal"),
            audioRecorder: MockAudioRecorder(),
            hotkeyMonitor: MockHotkeyMonitor(),
            pasteController: PasteController(
                pasteboard: MockPasteboardClient(),
                targetProvider: MockTargetProvider(target: nil),
                inputDriver: MockPasteInputDriver()
            ),
            permissionChecker: permissions,
            notifier: MockNotifier(),
            tempDirectory: tempDir.appendingPathComponent("wavs-overlay-restored", isDirectory: true),
            userDefaults: defaults
        )
        XCTAssertFalse(restored.isOverlayEnabled)
        XCTAssertFalse(restored.uiState.isOverlayEnabled)
        XCTAssertEqual(restored.uiState.overlayState, .hidden)
    }
}
