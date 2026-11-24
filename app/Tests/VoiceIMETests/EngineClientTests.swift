import Foundation
import XCTest
@testable import VoiceIMECore

/// 偽のPython認識エンジンを使ってJSONLプロトコル通信・キャンセル・エラー・異常終了後の自動再起動を検証するテスト。
@MainActor
final class EngineClientTests: XCTestCase {
    private var tempDir: URL!

    override func setUp() async throws {
        try await super.setUp()
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("voiceime-engine-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        if let tempDir {
            try? FileManager.default.removeItem(at: tempDir)
        }
        try await super.tearDown()
    }

    private func fakeEngineScriptURL() throws -> URL {
        guard let url = Bundle.module.url(forResource: "fake_engine", withExtension: "py", subdirectory: "Fixtures") else {
            throw NSError(domain: "EngineClientTests", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "Fixtures/fake_engine.py がテストバンドルに見つかりません。",
            ])
        }
        return url
    }

    private func makeLaunchConfig(extraEnv: [String: String] = [:]) throws -> EngineLaunchConfig {
        let scriptURL = try fakeEngineScriptURL()
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        for (k, v) in extraEnv {
            env[k] = v
        }
        return EngineLaunchConfig(
            executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
            arguments: ["-u", scriptURL.path],
            currentDirectoryURL: tempDir,
            environment: env
        )
    }

    func testProtocolEncodingMatchesEngineProtocolSpec() throws {
        let startData = try EngineProtocolCodec.encodeLine(
            .start(sessionId: "s-0001", app: TargetAppInfo(bundleId: "com.apple.dt.Xcode", name: "Xcode"))
        )
        XCTAssertEqual(startData.last, 0x0A)
        let startObj = try XCTUnwrap(JSONSerialization.jsonObject(with: startData) as? [String: Any])
        XCTAssertEqual(startObj["type"] as? String, "start")
        XCTAssertEqual(startObj["session_id"] as? String, "s-0001")
        let appObj = try XCTUnwrap(startObj["app"] as? [String: String])
        XCTAssertEqual(appObj["bundle_id"], "com.apple.dt.Xcode")
        XCTAssertEqual(appObj["name"], "Xcode")

        let segData = try EngineProtocolCodec.encodeLine(
            .segment(sessionId: "s-0001", seq: 0, wavPath: "/tmp/voiceime/s-0001-0.wav")
        )
        let segObj = try XCTUnwrap(JSONSerialization.jsonObject(with: segData) as? [String: Any])
        XCTAssertEqual(segObj["type"] as? String, "segment")
        XCTAssertEqual(segObj["session_id"] as? String, "s-0001")
        XCTAssertEqual(segObj["seq"] as? Int, 0)
        XCTAssertEqual(segObj["wav_path"] as? String, "/tmp/voiceime/s-0001-0.wav")

        let finishData = try EngineProtocolCodec.encodeLine(.finish(sessionId: "s-0001", mode: .formatted))
        let finishObj = try XCTUnwrap(JSONSerialization.jsonObject(with: finishData) as? [String: Any])
        XCTAssertEqual(finishObj["type"] as? String, "finish")
        XCTAssertEqual(finishObj["session_id"] as? String, "s-0001")
        XCTAssertEqual(finishObj["mode"] as? String, "formatted")

        let cancelData = try EngineProtocolCodec.encodeLine(.cancel(sessionId: "s-0001"))
        let cancelObj = try XCTUnwrap(JSONSerialization.jsonObject(with: cancelData) as? [String: Any])
        XCTAssertEqual(cancelObj["type"] as? String, "cancel")
        XCTAssertEqual(cancelObj["session_id"] as? String, "s-0001")

        let shutdownData = try EngineProtocolCodec.encodeLine(.shutdown)
        let shutdownObj = try XCTUnwrap(JSONSerialization.jsonObject(with: shutdownData) as? [String: Any])
        XCTAssertEqual(shutdownObj["type"] as? String, "shutdown")
    }

    func testStartEncodingHandlesScreenTextTruncationAndOmitsWhenEmpty() throws {
        let app = TargetAppInfo(bundleId: "com.apple.dt.Xcode", name: "Xcode")

        // screenText 未指定・空文字・空白のみの場合は JSON に screen_text 欄を出さない。
        for candidate in [nil, "", "   ", "\n\t  \n"] {
            let data = try EngineProtocolCodec.encodeLine(
                .start(sessionId: "s-0001", app: app, screenText: candidate)
            )
            let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertFalse(
                obj.keys.contains("screen_text"),
                "空のscreenTextでscreen_text欄が出力されました: \(String(describing: candidate))"
            )
        }

        // 通常テキスト（複数行）は1行JSONとして正しくエンコードされる。
        let normalData = try EngineProtocolCodec.encodeLine(
            .start(sessionId: "s-0001", app: app, screenText: "Hungarian Matching\nPyTorch DataLoader")
        )
        let normalLine = try XCTUnwrap(String(data: normalData, encoding: .utf8))
        XCTAssertEqual(normalLine.filter { $0 == "\n" }.count, 1) // 末尾改行のみ
        let normalObj = try XCTUnwrap(JSONSerialization.jsonObject(with: normalData) as? [String: Any])
        XCTAssertEqual(normalObj["screen_text"] as? String, "Hungarian Matching\nPyTorch DataLoader")

        // 4,000字を超える場合は4,000字で切り詰められる。
        let overLimit = String(repeating: "あ", count: 4_500)
        let truncatedData = try EngineProtocolCodec.encodeLine(
            .start(sessionId: "s-0001", app: app, screenText: overLimit)
        )
        let truncatedObj = try XCTUnwrap(JSONSerialization.jsonObject(with: truncatedData) as? [String: Any])
        let encodedScreenText = try XCTUnwrap(truncatedObj["screen_text"] as? String)
        XCTAssertEqual(encodedScreenText.count, 4_000)
        XCTAssertEqual(encodedScreenText, String(repeating: "あ", count: 4_000))
    }

    func testFakeEngineAcceptsStartWithScreenTextAndReturnsResult() async throws {
        let logFile = tempDir.appendingPathComponent("screen-text-engine.log")
        let client = EngineClient(
            launchConfig: try makeLaunchConfig(extraEnv: ["FAKE_ENGINE_LOG_FILE": logFile.path]),
            restartBackoffSeconds: [0.05]
        )

        let readyExp = expectation(description: "ready")
        let resultExp = expectation(description: "result")
        var receivedResult: EngineResultEvent?

        client.onEvent = { event in
            switch event {
            case .ready:
                readyExp.fulfill()
            case let .result(result):
                receivedResult = result
                resultExp.fulfill()
            case let .error(err):
                XCTFail("screen_text付きstartでエラーになりました: \(err.message)")
            default:
                break
            }
        }

        client.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        let wav = tempDir.appendingPathComponent("s-0001-0.wav")
        try WavWriter.write(samples: [Int16](repeating: 1000, count: 320), to: wav)

        let longScreenText = "Hungarian Matching\n" + String(repeating: "漢", count: 4_200)
        try client.send(.start(
            sessionId: "s-0001",
            app: TargetAppInfo(bundleId: "com.apple.Preview", name: "Preview"),
            screenText: longScreenText
        ))
        try client.send(.segment(sessionId: "s-0001", seq: 0, wavPath: wav.path))
        try client.send(.finish(sessionId: "s-0001", mode: .formatted))

        await fulfillment(of: [resultExp], timeout: 5.0)
        XCTAssertEqual(receivedResult?.sessionId, "s-0001")
        XCTAssertEqual(receivedResult?.text, "整形済み(0):wav_ok=true")
        XCTAssertEqual(receivedResult?.formatOk, true)

        await client.stop()

        let logLines = try String(contentsOf: logFile, encoding: .utf8)
            .split(separator: "\n")
            .map(String.init)
        XCTAssertEqual(logLines.count, 4) // start, segment, finish, shutdown
        let startObj = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(logLines[0].utf8)) as? [String: Any]
        )
        XCTAssertEqual(startObj["type"] as? String, "start")
        let receivedScreenText = try XCTUnwrap(startObj["screen_text"] as? String)
        XCTAssertEqual(receivedScreenText.count, 4_000)
        XCTAssertTrue(receivedScreenText.hasPrefix("Hungarian Matching\n"))
    }

    func testFullSessionRoundTripWithFakeEngine() async throws {
        let logFile = tempDir.appendingPathComponent("engine.log")
        let client = EngineClient(
            launchConfig: try makeLaunchConfig(extraEnv: ["FAKE_ENGINE_LOG_FILE": logFile.path]),
            restartBackoffSeconds: [0.05]
        )

        let readyExp = expectation(description: "ready")
        let partial0Exp = expectation(description: "partial 0")
        let partial1Exp = expectation(description: "partial 1")
        let resultExp = expectation(description: "result")

        var receivedResult: EngineResultEvent?
        var receivedReady: EngineReadyEvent?

        client.onEvent = { event in
            switch event {
            case let .ready(info):
                receivedReady = info
                readyExp.fulfill()
            case let .partial(partial):
                if partial.sessionId == "s-0001" && partial.seq == 0 {
                    partial0Exp.fulfill()
                } else if partial.sessionId == "s-0001" && partial.seq == 1 {
                    partial1Exp.fulfill()
                }
            case let .result(result):
                receivedResult = result
                resultExp.fulfill()
            case let .error(err):
                XCTFail("予期しないエラー: \(err.message)")
            }
        }

        client.start()
        await fulfillment(of: [readyExp], timeout: 5.0)
        XCTAssertTrue(client.isReady)
        XCTAssertEqual(receivedReady?.asr, "fake-asr-v1")
        XCTAssertEqual(receivedReady?.formatter, "fake-fmt-v1")

        let wav0 = tempDir.appendingPathComponent("s-0001-0.wav")
        let wav1 = tempDir.appendingPathComponent("s-0001-1.wav")
        try WavWriter.write(samples: [Int16](repeating: 1000, count: 320), to: wav0)
        try WavWriter.write(samples: [Int16](repeating: 2000, count: 320), to: wav1)

        try client.send(.start(sessionId: "s-0001", app: TargetAppInfo(bundleId: "com.apple.Notes", name: "Notes")))
        try client.send(.segment(sessionId: "s-0001", seq: 0, wavPath: wav0.path))
        try client.send(.segment(sessionId: "s-0001", seq: 1, wavPath: wav1.path))
        try client.send(.finish(sessionId: "s-0001", mode: .formatted))

        await fulfillment(of: [partial0Exp, partial1Exp, resultExp], timeout: 5.0)
        XCTAssertEqual(receivedResult?.sessionId, "s-0001")
        XCTAssertEqual(receivedResult?.text, "整形済み(0,1):wav_ok=true")
        XCTAssertEqual(receivedResult?.formatOk, true)
        XCTAssertEqual(receivedResult?.totalLatencyS, 0.31)

        await client.stop()
        XCTAssertEqual(client.state, .stopped)

        let logLines = try String(contentsOf: logFile, encoding: .utf8)
            .split(separator: "\n")
            .map(String.init)
        XCTAssertEqual(logLines.count, 5) // start, segment0, segment1, finish, shutdown
        XCTAssertTrue(logLines.last?.contains("\"shutdown\"") == true)
    }

    func testCancelDiscardsSessionAndAllowsNextSession() async throws {
        let client = EngineClient(launchConfig: try makeLaunchConfig(), restartBackoffSeconds: [0.05])
        let readyExp = expectation(description: "ready")
        let secondResultExp = expectation(description: "second result")
        var results: [EngineResultEvent] = []

        client.onEvent = { event in
            switch event {
            case .ready:
                readyExp.fulfill()
            case let .result(result):
                results.append(result)
                if result.sessionId == "s-0002" {
                    secondResultExp.fulfill()
                }
            default:
                break
            }
        }

        client.start()
        await fulfillment(of: [readyExp], timeout: 5.0)

        let wav = tempDir.appendingPathComponent("s.wav")
        try WavWriter.write(samples: [Int16](repeating: 1000, count: 320), to: wav)

        try client.send(.start(sessionId: "s-0001", app: TargetAppInfo(bundleId: "com.test", name: "Test")))
        try client.send(.segment(sessionId: "s-0001", seq: 0, wavPath: wav.path))
        try client.send(.cancel(sessionId: "s-0001"))

        try client.send(.start(sessionId: "s-0002", app: TargetAppInfo(bundleId: "com.test", name: "Test")))
        try client.send(.segment(sessionId: "s-0002", seq: 0, wavPath: wav.path))
        try client.send(.finish(sessionId: "s-0002", mode: .formatted))

        await fulfillment(of: [secondResultExp], timeout: 5.0)
        XCTAssertEqual(results.count, 1)
        XCTAssertEqual(results.first?.sessionId, "s-0002")

        await client.stop()
    }

    func testUnexpectedExitNotifiesAndAutomaticallyRestartsUntilReady() async throws {
        let marker = tempDir.appendingPathComponent("crashed.marker")
        let client = EngineClient(
            launchConfig: try makeLaunchConfig(extraEnv: ["FAKE_ENGINE_CRASH_ONCE_MARKER": marker.path]),
            restartBackoffSeconds: [0.05, 0.1]
        )

        let crashExp = expectation(description: "crash reported")
        let readyAfterRestartExp = expectation(description: "ready after restart")
        var crashInfo: EngineCrashInfo?

        client.onUnexpectedExit = { info in
            crashInfo = info
            crashExp.fulfill()
        }
        client.onEvent = { event in
            if case .ready = event {
                readyAfterRestartExp.fulfill()
            }
        }

        client.start()
        await fulfillment(of: [crashExp, readyAfterRestartExp], timeout: 5.0, enforceOrder: true)

        XCTAssertEqual(crashInfo?.exitStatus, 42)
        XCTAssertTrue(crashInfo?.stderrSummary.contains("simulated startup crash") == true)
        XCTAssertTrue(client.isReady)

        await client.stop()
    }

    func testResolveDefaultBuildsUvRunCommandForProjectRoot() throws {
        let fakeRepo = tempDir.appendingPathComponent("repo", isDirectory: true)
        try FileManager.default.createDirectory(
            at: fakeRepo.appendingPathComponent("src/voiceime", isDirectory: true),
            withIntermediateDirectories: true
        )
        try Data("name = \"voiceime\"\n".utf8)
            .write(to: fakeRepo.appendingPathComponent("pyproject.toml"))

        let fakeUV = tempDir.appendingPathComponent("fake-uv")
        try Data("#!/bin/sh\n".utf8).write(to: fakeUV)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: fakeUV.path)

        let config = try EngineLaunchConfig.resolveDefault(
            environment: [
                "VOICEIME_PROJECT_DIR": fakeRepo.path,
                "VOICEIME_UV_PATH": fakeUV.path,
                "PATH": "/usr/bin:/bin",
            ]
        )

        XCTAssertEqual(config.executableURL.path, fakeUV.path)
        XCTAssertEqual(
            config.arguments,
            ["run", "--project", fakeRepo.standardizedFileURL.path, "python", "-m", "voiceime.engine"]
        )
        XCTAssertEqual(config.currentDirectoryURL?.path, fakeRepo.standardizedFileURL.path)
    }
}
