import Darwin
import Foundation
import os

/// 認識エンジン子プロセスの起動設定。
public struct EngineLaunchConfig: Sendable, Equatable {
    public let executableURL: URL
    public let arguments: [String]
    public let currentDirectoryURL: URL?
    public let environment: [String: String]

    public init(
        executableURL: URL,
        arguments: [String],
        currentDirectoryURL: URL? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) {
        self.executableURL = executableURL
        self.arguments = arguments
        self.currentDirectoryURL = currentDirectoryURL
        self.environment = environment
    }

    /// 既定の起動コマンド（`uv run --project <リポジトリ> python -m voiceime.engine`）を環境とバンドル情報から組み立てる。
    public static func resolveDefault(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundle: Bundle = .main,
        fileManager: FileManager = .default
    ) throws -> EngineLaunchConfig {
        let projectRoot = try resolveProjectRoot(
            environment: environment,
            bundle: bundle,
            fileManager: fileManager
        )
        let uvURL = try resolveUVExecutable(
            environment: environment,
            fileManager: fileManager
        )

        var mergedEnv = environment
        let home = fileManager.homeDirectoryForCurrentUser.path
        let extraPaths = [
            "\(home)/.local/bin",
            "\(home)/.cargo/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]
        let existingPath = mergedEnv["PATH"] ?? ""
        let existingComponents = existingPath.split(separator: ":").map(String.init)
        var finalComponents = existingComponents
        for candidate in extraPaths where !finalComponents.contains(candidate) {
            finalComponents.append(candidate)
        }
        mergedEnv["PATH"] = finalComponents.joined(separator: ":")
        mergedEnv["PYTHONUNBUFFERED"] = "1"

        return EngineLaunchConfig(
            executableURL: uvURL,
            arguments: [
                "run",
                "--project",
                projectRoot.path,
                "python",
                "-m",
                "voiceime.engine",
            ],
            currentDirectoryURL: projectRoot,
            environment: mergedEnv
        )
    }

    /// プロジェクトのルートディレクトリを環境変数・Info.plist・上位ディレクトリ探索の順で解決する。
    public static func resolveProjectRoot(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundle: Bundle = .main,
        fileManager: FileManager = .default
    ) throws -> URL {
        if let envPath = environment["VOICEIME_PROJECT_DIR"], !envPath.isEmpty {
            let url = URL(fileURLWithPath: (envPath as NSString).expandingTildeInPath).standardizedFileURL
            if isProjectRoot(url, fileManager: fileManager) {
                return url
            }
            throw EngineClientError.invalidProjectRoot(url.path)
        }

        if let plistPath = bundle.object(forInfoDictionaryKey: "VoiceIMEProjectRoot") as? String,
           !plistPath.isEmpty {
            let url = URL(fileURLWithPath: plistPath).standardizedFileURL
            if isProjectRoot(url, fileManager: fileManager) {
                return url
            }
        }

        let searchSeeds = [
            URL(fileURLWithPath: fileManager.currentDirectoryPath),
            bundle.bundleURL,
            bundle.executableURL?.deletingLastPathComponent(),
        ].compactMap { $0?.standardizedFileURL }

        for seed in searchSeeds {
            var cursor = seed
            for _ in 0 ..< 8 {
                if isProjectRoot(cursor, fileManager: fileManager) {
                    return cursor
                }
                let parent = cursor.deletingLastPathComponent()
                if parent.path == cursor.path {
                    break
                }
                cursor = parent
            }
        }

        throw EngineClientError.projectRootNotFound
    }

    /// `uv` 実行ファイルを環境変数・PATH・標準インストール先から探す。
    public static func resolveUVExecutable(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default
    ) throws -> URL {
        if let explicit = environment["VOICEIME_UV_PATH"], !explicit.isEmpty {
            let expanded = (explicit as NSString).expandingTildeInPath
            if fileManager.isExecutableFile(atPath: expanded) {
                return URL(fileURLWithPath: expanded)
            }
            throw EngineClientError.uvNotFound(expanded)
        }

        var candidates: [String] = []
        if let pathEnv = environment["PATH"] {
            for dir in pathEnv.split(separator: ":") {
                candidates.append("\(dir)/uv")
            }
        }
        let home = fileManager.homeDirectoryForCurrentUser.path
        candidates.append(contentsOf: [
            "\(home)/.local/bin/uv",
            "\(home)/.cargo/bin/uv",
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv",
        ])

        for candidate in candidates where fileManager.isExecutableFile(atPath: candidate) {
            return URL(fileURLWithPath: candidate)
        }
        throw EngineClientError.uvNotFound(nil)
    }

    private static func isProjectRoot(_ url: URL, fileManager: FileManager) -> Bool {
        let pyproject = url.appendingPathComponent("pyproject.toml").path
        let packageDir = url.appendingPathComponent("src/voiceime").path
        var isDir: ObjCBool = false
        return fileManager.fileExists(atPath: pyproject)
            && fileManager.fileExists(atPath: packageDir, isDirectory: &isDir)
            && isDir.boolValue
    }
}

/// エンジン起動・通信に関わるエラー。
public enum EngineClientError: Error, LocalizedError, Equatable, Sendable {
    case projectRootNotFound
    case invalidProjectRoot(String)
    case uvNotFound(String?)
    case engineNotRunning
    case writeFailed(String)
    case launchFailed(String)

    public var errorDescription: String? {
        switch self {
        case .projectRootNotFound:
            return "voiceIMEプロジェクトのルート（pyproject.toml）が見つかりません。環境変数 VOICEIME_PROJECT_DIR を設定してください。"
        case let .invalidProjectRoot(path):
            return "指定されたVOICEIME_PROJECT_DIRにpyproject.tomlとsrc/voiceimeが見つかりません: \(path)"
        case let .uvNotFound(path):
            if let path {
                return "指定されたuvが見つかりません: \(path)"
            }
            return "uvコマンドが見つかりません。uvをインストールするか、環境変数 VOICEIME_UV_PATH を設定してください。"
        case .engineNotRunning:
            return "認識エンジンが起動していません。"
        case let .writeFailed(detail):
            return "認識エンジンへのメッセージ送信に失敗しました: \(detail)"
        case let .launchFailed(detail):
            return "認識エンジンの起動に失敗しました: \(detail)"
        }
    }
}

/// 認識エンジンのライフサイクル状態。
public enum EngineLifecycleState: Sendable, Equatable {
    case stopped
    case starting
    case ready(EngineReadyEvent)
    case restarting(attempt: Int)
    case failed(String)

    public var isReady: Bool {
        if case .ready = self { return true }
        return false
    }
}

/// 認識エンジン異常終了時の診断情報。
public struct EngineCrashInfo: Sendable, Equatable {
    public let exitStatus: Int32
    public let wasUncaughtSignal: Bool
    public let stderrSummary: String

    public init(exitStatus: Int32, wasUncaughtSignal: Bool, stderrSummary: String) {
        self.exitStatus = exitStatus
        self.wasUncaughtSignal = wasUncaughtSignal
        self.stderrSummary = stderrSummary
    }
}

/// 子プロセスの標準出力・標準エラー末尾ログを別スレッドで安全に保持する補助コンテナ。
private final class StderrRingBuffer: @unchecked Sendable {
    private let lock = OSAllocatedUnfairLock(initialState: [String]())
    private let maxLines: Int

    init(maxLines: Int = 20) {
        self.maxLines = maxLines
    }

    func append(_ line: String) {
        lock.withLock { lines in
            lines.append(line)
            if lines.count > maxLines {
                lines.removeFirst(lines.count - maxLines)
            }
        }
    }

    func summary() -> String {
        lock.withLock { lines in
            lines.suffix(5).joined(separator: "\n")
        }
    }
}

/// 1回分のエンジン子プロセスとパイプの所有・非同期書き込みを担う内部ハンドル。
private final class RunningEngineProcess: @unchecked Sendable {
    let generation: UInt64
    let process: Process
    let stdinPipe: Pipe
    let stdoutPipe: Pipe
    let stderrPipe: Pipe
    let stderrBuffer = StderrRingBuffer()
    private let writeQueue: DispatchQueue
    private let stateLock = OSAllocatedUnfairLock(initialState: false) // stdinClosed

    init(generation: UInt64, process: Process, stdinPipe: Pipe, stdoutPipe: Pipe, stderrPipe: Pipe) {
        self.generation = generation
        self.process = process
        self.stdinPipe = stdinPipe
        self.stdoutPipe = stdoutPipe
        self.stderrPipe = stderrPipe
        self.writeQueue = DispatchQueue(label: "com.voiceime.engine.stdin.\(generation)")
    }

    func writeAsync(_ data: Data, onError: @escaping @Sendable (String) -> Void) {
        writeQueue.async { [weak self] in
            guard let self else { return }
            let closed = self.stateLock.withLock { $0 }
            guard !closed else { return }
            do {
                try self.stdinPipe.fileHandleForWriting.write(contentsOf: data)
            } catch {
                onError(error.localizedDescription)
            }
        }
    }

    func writeAndCloseSynchronously(_ data: Data) {
        writeQueue.sync {
            let alreadyClosed = stateLock.withLock { closed -> Bool in
                if closed { return true }
                closed = true
                return false
            }
            guard !alreadyClosed else { return }
            try? stdinPipe.fileHandleForWriting.write(contentsOf: data)
            try? stdinPipe.fileHandleForWriting.close()
        }
    }

    func closeStdinAsync() {
        writeQueue.async { [weak self] in
            guard let self else { return }
            let alreadyClosed = self.stateLock.withLock { closed -> Bool in
                if closed { return true }
                closed = true
                return false
            }
            guard !alreadyClosed else { return }
            try? self.stdinPipe.fileHandleForWriting.close()
        }
    }
}

/// Python認識エンジンを子プロセスとして管理し、標準入出力のJSONL通信と異常終了時の自動再起動を行うクライアント。
@MainActor
public final class EngineClient {
    private nonisolated static let logger = Logger(subsystem: "com.voiceime.app", category: "EngineClient")

    public let launchConfig: EngineLaunchConfig
    public let restartBackoffSeconds: [TimeInterval]
    public let shutdownTimeoutSeconds: TimeInterval

    public private(set) var state: EngineLifecycleState = .stopped {
        didSet {
            if state != oldValue {
                onStateChange?(state)
            }
        }
    }

    public var isReady: Bool { state.isReady }

    public var onEvent: ((EngineEvent) -> Void)?
    public var onStateChange: ((EngineLifecycleState) -> Void)?
    public var onUnexpectedExit: ((EngineCrashInfo) -> Void)?

    private var currentProcess: RunningEngineProcess?
    private var generation: UInt64 = 0
    private var isStopping = false
    private var restartAttempt = 0
    private var restartTask: Task<Void, Never>?

    public init(
        launchConfig: EngineLaunchConfig,
        restartBackoffSeconds: [TimeInterval] = [1.0, 2.0, 4.0, 8.0, 10.0],
        shutdownTimeoutSeconds: TimeInterval = 1.5
    ) {
        self.launchConfig = launchConfig
        self.restartBackoffSeconds = restartBackoffSeconds.isEmpty ? [1.0] : restartBackoffSeconds
        self.shutdownTimeoutSeconds = shutdownTimeoutSeconds
    }

    /// 認識エンジンを起動し、`ready` の受信を待ち始める。
    public func start() {
        // 子プロセス終了直後のパイプ書き込みでSIGPIPEによりアプリが強制終了するのを防ぐ。
        signal(SIGPIPE, SIG_IGN)
        isStopping = false
        restartTask?.cancel()
        restartTask = nil
        restartAttempt = 0
        launchProcess()
    }

    /// アプリから認識エンジンへJSONコマンドを1行送信する。
    public func send(_ command: EngineCommand) throws {
        guard let running = currentProcess, running.process.isRunning else {
            throw EngineClientError.engineNotRunning
        }
        let lineData = try EngineProtocolCodec.encodeLine(command)
        let currentGen = running.generation
        running.writeAsync(lineData) { [weak self] message in
            Task { @MainActor [weak self] in
                guard let self, self.generation == currentGen, !self.isStopping else { return }
                Self.logger.error("エンジンへの書き込み失敗: \(message, privacy: .public)")
            }
        }
    }

    /// `shutdown` を送って安全に停止する。タイムアウトした場合は `SIGTERM` を送る。
    public func stop() async {
        isStopping = true
        restartTask?.cancel()
        restartTask = nil

        guard let running = currentProcess else {
            state = .stopped
            return
        }
        currentProcess = nil
        generation &+= 1

        if let shutdownData = try? EngineProtocolCodec.encodeLine(.shutdown) {
            running.writeAsync(shutdownData) { _ in }
        }
        running.closeStdinAsync()

        let deadline = Date().addingTimeInterval(shutdownTimeoutSeconds)
        while running.process.isRunning && Date() < deadline {
            try? await Task.sleep(for: .milliseconds(25))
        }
        if running.process.isRunning {
            running.process.terminate()
        }
        state = .stopped
    }

    /// アプリ終了コールバック（同期）から呼ぶための停止処理。
    public func stopSynchronouslyForAppTermination() {
        isStopping = true
        restartTask?.cancel()
        restartTask = nil

        guard let running = currentProcess else {
            state = .stopped
            return
        }
        currentProcess = nil
        generation &+= 1

        if let shutdownData = try? EngineProtocolCodec.encodeLine(.shutdown) {
            running.writeAndCloseSynchronously(shutdownData)
        } else {
            running.closeStdinAsync()
        }

        let deadline = Date().addingTimeInterval(min(shutdownTimeoutSeconds, 1.0))
        while running.process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.02)
        }
        if running.process.isRunning {
            running.process.terminate()
        }
        state = .stopped
    }

    private func launchProcess() {
        generation &+= 1
        let gen = generation
        state = restartAttempt == 0 ? .starting : .restarting(attempt: restartAttempt)

        let process = Process()
        process.executableURL = launchConfig.executableURL
        process.arguments = launchConfig.arguments
        process.currentDirectoryURL = launchConfig.currentDirectoryURL
        process.environment = launchConfig.environment

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let running = RunningEngineProcess(
            generation: gen,
            process: process,
            stdinPipe: stdinPipe,
            stdoutPipe: stdoutPipe,
            stderrPipe: stderrPipe
        )
        currentProcess = running

        process.terminationHandler = { [weak self] terminatedProcess in
            let status = terminatedProcess.terminationStatus
            let wasSignal = terminatedProcess.terminationReason == .uncaughtSignal
            let stderrSummary = running.stderrBuffer.summary()
            Task { @MainActor [weak self] in
                self?.handleProcessTermination(
                    generation: gen,
                    exitStatus: status,
                    wasUncaughtSignal: wasSignal,
                    stderrSummary: stderrSummary
                )
            }
        }

        do {
            try process.run()
        } catch {
            currentProcess = nil
            let detail = error.localizedDescription
            Self.logger.error("認識エンジン起動失敗: \(detail, privacy: .public)")
            state = .failed(EngineClientError.launchFailed(detail).localizedDescription)
            scheduleRestart(afterCrash: EngineCrashInfo(exitStatus: -1, wasUncaughtSignal: false, stderrSummary: detail))
            return
        }

        startStdoutReader(handle: stdoutPipe.fileHandleForReading, generation: gen)
        startStderrReader(handle: stderrPipe.fileHandleForReading, buffer: running.stderrBuffer)
    }

    /// 子プロセスの標準出力を改行区切りで読み取り、JSONイベントをメインアクターへ届ける。
    private func startStdoutReader(handle: FileHandle, generation gen: UInt64) {
        let queue = DispatchQueue(label: "com.voiceime.engine.stdout.\(gen)")
        queue.async { [weak self] in
            var buffer = Data()
            while true {
                let chunk = handle.availableData
                if chunk.isEmpty {
                    break
                }
                buffer.append(chunk)
                while let newlineIndex = buffer.firstIndex(of: 0x0A) {
                    var line = Data(buffer[..<newlineIndex])
                    buffer.removeSubrange(...newlineIndex)
                    if line.last == 0x0D { // CRLF対策
                        line.removeLast()
                    }
                    guard !line.isEmpty else { continue }
                    let capturedLine = line
                    Task { @MainActor [weak self] in
                        self?.handleStdoutLine(capturedLine, generation: gen)
                    }
                }
            }
            if !buffer.isEmpty {
                let trailing = buffer
                Task { @MainActor [weak self] in
                    self?.handleStdoutLine(trailing, generation: gen)
                }
            }
            try? handle.close()
        }
    }

    /// 子プロセスの標準エラーを診断用リングバッファへ記録する。
    private func startStderrReader(handle: FileHandle, buffer ringBuffer: StderrRingBuffer) {
        let queue = DispatchQueue(label: "com.voiceime.engine.stderr")
        queue.async {
            var pending = Data()
            while true {
                let chunk = handle.availableData
                if chunk.isEmpty {
                    break
                }
                pending.append(chunk)
                while let newlineIndex = pending.firstIndex(of: 0x0A) {
                    let lineData = Data(pending[..<newlineIndex])
                    pending.removeSubrange(...newlineIndex)
                    if let text = String(data: lineData, encoding: .utf8), !text.isEmpty {
                        ringBuffer.append(text)
                        Self.logger.debug("[engine stderr] \(text, privacy: .public)")
                    }
                }
            }
            if !pending.isEmpty, let text = String(data: pending, encoding: .utf8), !text.isEmpty {
                ringBuffer.append(text)
            }
            try? handle.close()
        }
    }

    private func handleStdoutLine(_ lineData: Data, generation gen: UInt64) {
        guard gen == generation, !isStopping else { return }
        do {
            let event = try EngineProtocolCodec.decodeLine(lineData)
            if case let .ready(readyInfo) = event {
                restartAttempt = 0
                state = .ready(readyInfo)
            }
            onEvent?(event)
        } catch {
            let raw = String(data: lineData, encoding: .utf8) ?? "<binary>"
            Self.logger.warning("エンジン出力のJSON解析に失敗しました: \(error.localizedDescription, privacy: .public) raw=\(raw, privacy: .public)")
        }
    }

    private func handleProcessTermination(
        generation gen: UInt64,
        exitStatus: Int32,
        wasUncaughtSignal: Bool,
        stderrSummary: String
    ) {
        guard gen == generation else { return }
        currentProcess = nil

        if isStopping {
            state = .stopped
            return
        }

        let crashInfo = EngineCrashInfo(
            exitStatus: exitStatus,
            wasUncaughtSignal: wasUncaughtSignal,
            stderrSummary: stderrSummary
        )
        Self.logger.error("認識エンジンが異常終了しました (code=\(exitStatus))")
        scheduleRestart(afterCrash: crashInfo)
    }

    private func scheduleRestart(afterCrash crashInfo: EngineCrashInfo) {
        restartAttempt += 1
        state = .restarting(attempt: restartAttempt)
        onUnexpectedExit?(crashInfo)

        let backoffIndex = min(restartAttempt - 1, restartBackoffSeconds.count - 1)
        let delay = restartBackoffSeconds[backoffIndex]
        let expectedGen = generation

        restartTask?.cancel()
        restartTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(delay))
            guard let self, !Task.isCancelled, !self.isStopping, self.generation == expectedGen else {
                return
            }
            self.launchProcess()
        }
    }
}
