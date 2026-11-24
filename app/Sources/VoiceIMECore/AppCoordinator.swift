import Foundation
import os

/// メニューバーアイコンが表す4つの状態。
public enum AppIconState: Sendable, Equatable {
    case idle
    case recording
    case processing
    case error
}

/// メニューに表示する「画面の文字を使う」機能の現在状態。
public enum ScreenTextStatus: Sendable, Equatable {
    /// オンかつ画面収録の権限が許可されている。
    case enabled
    /// ユーザーがメニューでオフにしている。
    case disabled
    /// 機能はオンだが、画面収録の権限が無い。
    case permissionMissing

    /// 状態の短い日本語表記。
    public var displayName: String {
        switch self {
        case .enabled:
            return "オン"
        case .disabled:
            return "オフ"
        case .permissionMissing:
            return "権限なし"
        }
    }

    /// メニュー項目へ表示するタイトル。
    public var menuTitle: String {
        "画面の文字を使う（\(displayName)）"
    }
}

/// メニューバー表示とオーバーレイへ渡す現在のアプリ状態スナップショット。
public struct AppUIState: Sendable, Equatable {
    public let iconState: AppIconState
    public let statusText: String
    public let hotkeyMode: HotkeyMode
    public let screenTextStatus: ScreenTextStatus
    public let isOverlayEnabled: Bool
    public let overlayState: OverlayState
    public let lastResultText: String?

    public init(
        iconState: AppIconState,
        statusText: String,
        hotkeyMode: HotkeyMode,
        screenTextStatus: ScreenTextStatus = .disabled,
        isOverlayEnabled: Bool = true,
        overlayState: OverlayState = .hidden,
        lastResultText: String?
    ) {
        self.iconState = iconState
        self.statusText = statusText
        self.hotkeyMode = hotkeyMode
        self.screenTextStatus = screenTextStatus
        self.isOverlayEnabled = isOverlayEnabled
        self.overlayState = overlayState
        self.lastResultText = lastResultText
    }
}

/// 音声パイプラインからメインアクターへ厳密なFIFO順で届けるイベント。
private enum AudioPipelineEvent: Sendable {
    case segment(sessionId: String, seq: Int, url: URL)
    case runtimeError(sessionId: String, message: String)
    case finished(
        sessionId: String,
        finalSegments: [(seq: Int, url: URL)],
        totalSegments: Int,
        allWavFiles: [URL],
        writeErrorMessage: String?
    )
}

/// 1録音セッション分のセグメント分割と一時WAV書き出しをシリアルキュー上で保持する状態。
private final class RecordingPipeline: @unchecked Sendable {
    let sessionId: String
    let tempDirectory: URL
    var segmenter: AudioSegmenter
    var nextSeq: Int = 0
    var wavFiles: [URL] = []
    var isCancelled: Bool = false

    init(sessionId: String, tempDirectory: URL, config: SegmenterConfig) {
        self.sessionId = sessionId
        self.tempDirectory = tempDirectory
        self.segmenter = AudioSegmenter(config: config)
    }

    func writeSegment(_ segment: AudioSegment) throws -> (seq: Int, url: URL) {
        let seq = nextSeq
        nextSeq += 1
        let filename = "\(sessionId)-\(seq).wav"
        let url = tempDirectory.appendingPathComponent(filename)
        try WavWriter.write(samples: segment.samples, to: url)
        wavFiles.append(url)
        return (seq, url)
    }
}

/// 録音・区間分割・認識エンジン通信・宛先照合付き貼り付け・状態表示を統合する司令塔。
@MainActor
public final class AppCoordinator {
    private nonisolated static let logger = Logger(subsystem: "com.voiceime.app", category: "AppCoordinator")
    private static let hotkeyModeDefaultsKey = "VoiceIME.HotkeyMode"
    private static let screenTextEnabledDefaultsKey = "VoiceIME.ScreenTextEnabled"
    public static let overlayEnabledDefaultsKey = "VoiceIME.OverlayEnabled"
    /// 録音開始時の前面ウィンドウ撮影・文字認識の既定タイムアウト。これを超えたら `screen_text` なしで `start` を送る。
    public static let defaultScreenTextTimeout: Duration = .milliseconds(300)

    /// 録音から結果受信までの1セッションの進行状態。
    private enum SessionState {
        case idle
        case recording(sessionId: String, target: PasteTarget?, pipeline: RecordingPipeline)
        case finishing(sessionId: String, target: PasteTarget?)
        case awaitingResult(sessionId: String, target: PasteTarget?)

        var isRecording: Bool {
            if case .recording = self { return true }
            return false
        }

        var isBusy: Bool {
            if case .idle = self { return false }
            return true
        }
    }

    /// 画面文字読み取り完了または時間切れまで `start` 送信を保留し、後続コマンドの順序を守るための状態。
    private struct PendingStartState {
        let sessionId: String
        let task: Task<Void, Never>
        var queuedCommands: [EngineCommand] = []
    }

    public private(set) var uiState: AppUIState {
        didSet {
            if uiState != oldValue {
                onUIStateChange?(uiState)
            }
        }
    }

    /// メニューの「画面の文字を使う」設定値（既定はオン）。
    public private(set) var isScreenTextEnabled: Bool

    /// メニューの「録音中の表示」設定値（既定はオン）。
    public var isOverlayEnabled: Bool {
        overlayStateMachine.isEnabled
    }

    public var onUIStateChange: ((AppUIState) -> Void)?
    /// 録音中の正規化音量レベル（0.0〜1.0）の変化通知。メニューバー再描画と分離して波形のみ高頻度更新する。
    public var onAudioLevelChange: ((Float) -> Void)?

    private let engineClient: EngineClient
    private let audioRecorder: AudioRecorderProtocol
    private let hotkeyMonitor: HotkeyMonitoring
    private let pasteController: PasteController
    private let permissionChecker: PermissionChecking
    private let notifier: UserNotifying
    private let screenTextReader: ScreenTextReading
    private let screenTextTimeout: Duration
    private let segmenterConfig: SegmenterConfig
    private let tempDirectory: URL
    private let userDefaults: UserDefaults?
    private let repastePreDelay: Duration
    private let doneAutoHideDelay: Duration
    private let errorAutoHideDelay: Duration

    private let audioQueue = DispatchQueue(label: "com.voiceime.app.audio-pipeline")
    private let pipelineContinuation: AsyncStream<AudioPipelineEvent>.Continuation
    private var pipelineConsumerTask: Task<Void, Never>?

    private var sessionCounter: Int = 0
    private var sessionState: SessionState = .idle
    private var pendingStart: PendingStartState?
    /// キャンセルや異常終了後に遅れて到着したWAVを漏れなく消せるようセッション単位で追跡する。
    private var trackedWavFiles: [String: [URL]] = [:]
    private var hotkeyStarted = false
    private var permissionRetryTask: Task<Void, Never>?
    private var startupPermissionTask: Task<Void, Never>?
    private var overlayStateMachine: OverlayStateMachine
    private var overlayAutoHideTask: Task<Void, Never>?

    public init(
        engineClient: EngineClient,
        audioRecorder: AudioRecorderProtocol = MicrophoneAudioRecorder(),
        hotkeyMonitor: HotkeyMonitoring = CGEventTapHotkeyMonitor(),
        pasteController: PasteController = PasteController(),
        permissionChecker: PermissionChecking = SystemPermissionChecker(),
        notifier: UserNotifying = SystemUserNotifier(),
        screenTextReader: ScreenTextReading = ScreenTextReader(),
        segmenterConfig: SegmenterConfig = .default,
        tempDirectory: URL? = nil,
        userDefaults: UserDefaults? = .standard,
        initialHotkeyMode: HotkeyMode? = nil,
        initialScreenTextEnabled: Bool? = nil,
        initialOverlayEnabled: Bool? = nil,
        screenTextTimeout: Duration = AppCoordinator.defaultScreenTextTimeout,
        repastePreDelay: Duration = .milliseconds(100),
        doneAutoHideDelay: Duration = OverlayMetrics.doneAutoHideDelay,
        errorAutoHideDelay: Duration = OverlayMetrics.errorAutoHideDelay
    ) {
        self.engineClient = engineClient
        self.audioRecorder = audioRecorder
        self.hotkeyMonitor = hotkeyMonitor
        self.pasteController = pasteController
        self.permissionChecker = permissionChecker
        self.notifier = notifier
        self.screenTextReader = screenTextReader
        self.screenTextTimeout = screenTextTimeout
        self.segmenterConfig = segmenterConfig
        self.tempDirectory = tempDirectory
            ?? FileManager.default.temporaryDirectory.appendingPathComponent("voiceime", isDirectory: true)
        self.userDefaults = userDefaults
        self.repastePreDelay = repastePreDelay
        self.doneAutoHideDelay = doneAutoHideDelay
        self.errorAutoHideDelay = errorAutoHideDelay

        let (stream, continuation) = AsyncStream<AudioPipelineEvent>.makeStream()
        self.pipelineContinuation = continuation

        let resolvedMode: HotkeyMode
        if let initialHotkeyMode {
            resolvedMode = initialHotkeyMode
        } else if let saved = userDefaults?.string(forKey: Self.hotkeyModeDefaultsKey),
                  let parsed = HotkeyMode(rawValue: saved) {
            resolvedMode = parsed
        } else {
            resolvedMode = .fnHold
        }

        let resolvedScreenTextEnabled: Bool
        if let initialScreenTextEnabled {
            resolvedScreenTextEnabled = initialScreenTextEnabled
        } else if let userDefaults, userDefaults.object(forKey: Self.screenTextEnabledDefaultsKey) != nil {
            resolvedScreenTextEnabled = userDefaults.bool(forKey: Self.screenTextEnabledDefaultsKey)
        } else {
            resolvedScreenTextEnabled = true
        }
        self.isScreenTextEnabled = resolvedScreenTextEnabled

        let resolvedOverlayEnabled: Bool
        if let initialOverlayEnabled {
            resolvedOverlayEnabled = initialOverlayEnabled
        } else if let userDefaults, userDefaults.object(forKey: Self.overlayEnabledDefaultsKey) != nil {
            resolvedOverlayEnabled = userDefaults.bool(forKey: Self.overlayEnabledDefaultsKey)
        } else {
            resolvedOverlayEnabled = true
        }
        self.overlayStateMachine = OverlayStateMachine(isEnabled: resolvedOverlayEnabled)

        let hasScreenPermission = permissionChecker.currentStatus().screenRecording
        let initialScreenStatus: ScreenTextStatus
        if !resolvedScreenTextEnabled {
            initialScreenStatus = .disabled
        } else {
            initialScreenStatus = hasScreenPermission ? .enabled : .permissionMissing
        }

        self.hotkeyMonitor.mode = resolvedMode
        self.uiState = AppUIState(
            iconState: .processing,
            statusText: "認識エンジン起動中...",
            hotkeyMode: resolvedMode,
            screenTextStatus: initialScreenStatus,
            isOverlayEnabled: resolvedOverlayEnabled,
            overlayState: .hidden,
            lastResultText: nil
        )

        wireCallbacks()
        startPipelineConsumer(stream)
    }

    /// エンジン起動・ホットキー監視開始・権限確認を一括で開始する。
    public func start() {
        ensureTempDirectory()
        notifier.requestAuthorizationIfAvailable()
        engineClient.start()

        hotkeyStarted = hotkeyMonitor.start()
        if !hotkeyStarted {
            scheduleHotkeyRetryIfNeeded()
        }

        startupPermissionTask?.cancel()
        startupPermissionTask = Task { [weak self] in
            guard let self else { return }
            _ = await self.permissionChecker.requestMicrophonePermissionIfNeeded()
            guard !Task.isCancelled else { return }
            self.notifyMissingPermissionsIfAny()
            self.refreshScreenRecordingPermission()
            if !self.hotkeyStarted && self.permissionChecker.currentStatus().inputMonitoring {
                self.hotkeyStarted = self.hotkeyMonitor.start()
            }
        }
    }

    /// ホットキー監視と認識エンジンを安全に停止し、残っている一時ファイルを消す。
    public func stop() async {
        startupPermissionTask?.cancel()
        startupPermissionTask = nil
        permissionRetryTask?.cancel()
        permissionRetryTask = nil
        cancelOverlayAutoHideTask()
        cancelAnyPendingStart()
        hotkeyMonitor.stop()
        hotkeyStarted = false

        if sessionState.isRecording {
            cancelRecording(sendCancelToEngine: false)
        } else {
            sessionState = .idle
            applyOverlayEvent(.recordingCancelled)
        }
        pipelineContinuation.finish()
        pipelineConsumerTask?.cancel()
        pipelineConsumerTask = nil

        cleanupAllTempFiles()
        await engineClient.stop()
    }

    /// `NSApplicationDelegate.applicationWillTerminate` から呼ぶ同期停止処理。
    public func stopSynchronouslyForAppTermination() {
        startupPermissionTask?.cancel()
        startupPermissionTask = nil
        permissionRetryTask?.cancel()
        permissionRetryTask = nil
        cancelOverlayAutoHideTask()
        cancelAnyPendingStart()
        hotkeyMonitor.stop()
        hotkeyStarted = false

        if sessionState.isRecording {
            cancelRecording(sendCancelToEngine: false)
        } else {
            sessionState = .idle
            applyOverlayEvent(.recordingCancelled)
        }
        pipelineContinuation.finish()
        pipelineConsumerTask?.cancel()
        pipelineConsumerTask = nil

        cleanupAllTempFiles()
        engineClient.stopSynchronouslyForAppTermination()
    }

    /// 起動キー方式を切り替えて設定を保存する。
    public func setHotkeyMode(_ mode: HotkeyMode) {
        hotkeyMonitor.mode = mode
        userDefaults?.set(mode.rawValue, forKey: Self.hotkeyModeDefaultsKey)
        if !hotkeyStarted {
            hotkeyStarted = hotkeyMonitor.start()
        }
        updateUIState(
            iconState: uiState.iconState,
            statusText: uiState.statusText,
            hotkeyMode: mode,
            lastResultText: uiState.lastResultText
        )
    }

    /// 「画面の文字を使う」機能のオン／オフを設定して保存し、画面収録権限と合わせて状態を更新する。
    public func setScreenTextEnabled(_ enabled: Bool) {
        isScreenTextEnabled = enabled
        userDefaults?.set(enabled, forKey: Self.screenTextEnabledDefaultsKey)
        let hasPermission = permissionChecker.currentStatus().screenRecording
        updateUIState(
            iconState: uiState.iconState,
            statusText: uiState.statusText,
            hotkeyMode: uiState.hotkeyMode,
            screenTextStatus: resolveScreenTextStatus(hasPermission: hasPermission),
            lastResultText: uiState.lastResultText
        )
    }

    /// メニュー操作から「画面の文字を使う」機能のオン／オフを切り替える。
    public func toggleScreenTextEnabled() {
        setScreenTextEnabled(!isScreenTextEnabled)
    }

    /// 「録音中の表示」オーバーレイのオン／オフを設定して保存し、表示状態へ即座に反映する。
    public func setOverlayEnabled(_ enabled: Bool) {
        userDefaults?.set(enabled, forKey: Self.overlayEnabledDefaultsKey)
        applyOverlayEvent(.setEnabled(enabled))
        if !enabled {
            onAudioLevelChange?(0)
        }
    }

    /// メニュー操作から「録音中の表示」のオン／オフを切り替える。
    public func toggleOverlayEnabled() {
        setOverlayEnabled(!isOverlayEnabled)
    }

    /// 画面収録の権限状態を最新化してメニュー表示へ反映する。
    public func refreshScreenRecordingPermission() {
        let hasPermission = permissionChecker.currentStatus().screenRecording
        updateUIState(
            iconState: uiState.iconState,
            statusText: uiState.statusText,
            hotkeyMode: uiState.hotkeyMode,
            screenTextStatus: resolveScreenTextStatus(hasPermission: hasPermission),
            lastResultText: uiState.lastResultText
        )
    }

    /// ユーザー操作に応じて画面収録の権限をシステムへ要求し、未許可であれば設定手順を通知する。
    public func requestScreenRecordingPermission() {
        let granted = permissionChecker.requestScreenRecordingPermission()
        updateUIState(
            iconState: uiState.iconState,
            statusText: uiState.statusText,
            hotkeyMode: uiState.hotkeyMode,
            screenTextStatus: resolveScreenTextStatus(hasPermission: granted),
            lastResultText: uiState.lastResultText
        )
        if !granted {
            notifier.notify(
                title: "VoiceIME 権限の確認",
                body: PermissionStatus.screenRecordingGuidanceMessage
            )
        }
    }

    /// 直前の認識・整形結果を現在の前面アプリへもう一度貼り付ける。
    public func repasteLastResult() {
        guard let text = uiState.lastResultText, !text.isEmpty else {
            return
        }
        Task { [weak self] in
            guard let self else { return }
            // メニューが閉じてフォーカスが前面アプリへ戻るのを少し待つ。
            if self.repastePreDelay > .zero {
                try? await Task.sleep(for: self.repastePreDelay)
            }
            let outcome = await self.pasteController.paste(text: text, expectedTarget: nil)
            switch outcome {
            case .pasted:
                self.applyOverlayEvent(.pasteSucceeded)
            case let .copiedFallback(reason):
                self.applyOverlayEvent(.pasteFallback(reason))
                self.notifier.notify(title: "VoiceIME", body: reason.userMessage)
            case .skippedEmpty:
                break
            }
        }
    }

    /// ホットキーイベントに応じた録音開始・停止・取り消しを処理する。
    public func handleHotkeyAction(_ action: HotkeyAction) {
        switch action {
        case .startRecording:
            startRecording()
        case .stopRecording:
            stopRecording()
        case .toggleRecording:
            if sessionState.isRecording {
                stopRecording()
            } else {
                startRecording()
            }
        case .cancelRecording:
            cancelRecording(sendCancelToEngine: true)
        }
    }

    // MARK: - Audio Pipeline Consumer

    private func startPipelineConsumer(_ stream: AsyncStream<AudioPipelineEvent>) {
        pipelineConsumerTask = Task { [weak self] in
            for await event in stream {
                guard let self, !Task.isCancelled else { break }
                self.handlePipelineEvent(event)
            }
        }
    }

    private func handlePipelineEvent(_ event: AudioPipelineEvent) {
        switch event {
        case let .segment(sessionId, seq, url):
            sendSegmentIfActive(sessionId: sessionId, seq: seq, url: url)
        case let .runtimeError(sessionId, message):
            handleRecorderRuntimeError(message, sessionId: sessionId)
        case let .finished(sessionId, finalSegments, totalSegments, allWavFiles, writeErrorMessage):
            completeStopRecording(
                sessionId: sessionId,
                finalSegments: finalSegments,
                totalSegments: totalSegments,
                allWavFiles: allWavFiles,
                writeErrorMessage: writeErrorMessage
            )
        }
    }

    // MARK: - Recording Lifecycle

    private func startRecording() {
        guard !sessionState.isBusy else {
            return
        }
        guard engineClient.isReady else {
            Self.logger.notice("エンジン準備完了前のため録音開始を無視しました。")
            switch engineClient.state {
            case .restarting, .failed:
                applyOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
            case .stopped, .starting, .ready:
                break
            }
            return
        }

        let permissions = permissionChecker.currentStatus()
        let latestScreenTextStatus = resolveScreenTextStatus(hasPermission: permissions.screenRecording)
        if uiState.screenTextStatus != latestScreenTextStatus {
            updateUIState(
                iconState: uiState.iconState,
                statusText: uiState.statusText,
                hotkeyMode: uiState.hotkeyMode,
                screenTextStatus: latestScreenTextStatus,
                lastResultText: uiState.lastResultText
            )
        }

        guard permissions.microphone else {
            applyOverlayEvent(.errorOccurred(message: "マイク権限がありません"))
            notifier.notify(title: "VoiceIME 権限の確認", body: RequiredPermission.microphone.guidanceMessage)
            return
        }

        ensureTempDirectory()
        sessionCounter += 1
        let sessionId = String(format: "s-%04d", sessionCounter)
        let target = pasteController.captureTarget()
        let appInfo = target?.appInfo ?? TargetAppInfo(bundleId: "", name: "")

        let pipeline = RecordingPipeline(
            sessionId: sessionId,
            tempDirectory: tempDirectory,
            config: segmenterConfig
        )
        sessionState = .recording(sessionId: sessionId, target: target, pipeline: pipeline)
        trackedWavFiles[sessionId] = []

        let continuation = pipelineContinuation
        do {
            // 画面の撮影・文字認識で録音の立ち上がりを遅らせないよう、先にマイク録音を即座に開始する。
            try audioRecorder.start(
                onSamples: { [weak self] samples in
                    self?.enqueueAudioSamples(samples, pipeline: pipeline, continuation: continuation)
                },
                onError: { errorMessage in
                    continuation.yield(.runtimeError(sessionId: sessionId, message: errorMessage))
                }
            )
        } catch {
            sessionState = .idle
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.errorOccurred(message: "録音開始エラー"))
            updateUIState(
                iconState: .error,
                statusText: "録音開始エラー",
                hotkeyMode: uiState.hotkeyMode,
                screenTextStatus: latestScreenTextStatus,
                lastResultText: uiState.lastResultText
            )
            notifier.notify(title: "VoiceIME エラー", body: error.localizedDescription)
            return
        }

        onAudioLevelChange?(0)
        recordOverlayEvent(.recordingStarted)
        updateUIState(
            iconState: .recording,
            statusText: "録音中（Escで取り消し）",
            hotkeyMode: uiState.hotkeyMode,
            screenTextStatus: latestScreenTextStatus,
            lastResultText: uiState.lastResultText
        )

        if isScreenTextEnabled && permissions.screenRecording {
            let preferredPid = target?.pid
            let reader = screenTextReader
            let timeout = screenTextTimeout
            let task = Task { [weak self] in
                let screenText = await reader.readFrontmostWindowText(
                    preferredPid: preferredPid,
                    timeout: timeout
                )
                guard let self, !Task.isCancelled else { return }
                self.finishPendingStart(
                    sessionId: sessionId,
                    app: appInfo,
                    screenText: screenText
                )
            }
            pendingStart = PendingStartState(sessionId: sessionId, task: task)
        } else {
            do {
                try engineClient.send(.start(sessionId: sessionId, app: appInfo, screenText: nil))
            } catch {
                abortStartAfterSendFailure(error, sessionId: sessionId, pipeline: pipeline)
            }
        }
    }

    private func stopRecording() {
        guard case let .recording(sessionId, target, pipeline) = sessionState else {
            return
        }

        let flushedTail: [Int16]
        do {
            flushedTail = try audioRecorder.stop()
        } catch {
            let hadPendingStart = cancelPendingStartIfMatching(sessionId: sessionId)
            sessionState = .idle
            onAudioLevelChange?(0)
            if !hadPendingStart {
                try? engineClient.send(.cancel(sessionId: sessionId))
            }
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.errorOccurred(message: "録音停止エラー"))
            restoreIdleOrEngineState()
            notifier.notify(title: "VoiceIME エラー", body: error.localizedDescription)
            return
        }

        // audioQueue上で処理中の先行セグメントも受け取れるよう .finishing 状態で待機する。
        sessionState = .finishing(sessionId: sessionId, target: target)
        onAudioLevelChange?(0)
        recordOverlayEvent(.processingStarted)
        updateUIState(
            iconState: .processing,
            statusText: "認識・整形中...",
            hotkeyMode: uiState.hotkeyMode,
            lastResultText: uiState.lastResultText
        )

        let continuation = pipelineContinuation
        // 進行中の音声チャンク処理がすべて終わった後に末尾区間とfinishを送るため、同じaudioQueueへ積む。
        audioQueue.async {
            guard !pipeline.isCancelled else { return }

            var finalSegments: [(seq: Int, url: URL)] = []
            var writeErrorMessage: String?

            if !flushedTail.isEmpty {
                for segment in pipeline.segmenter.push(samples: flushedTail) {
                    do {
                        finalSegments.append(try pipeline.writeSegment(segment))
                    } catch {
                        writeErrorMessage = error.localizedDescription
                        break
                    }
                }
            }

            if writeErrorMessage == nil, let tailSegment = pipeline.segmenter.finish() {
                do {
                    finalSegments.append(try pipeline.writeSegment(tailSegment))
                } catch {
                    writeErrorMessage = error.localizedDescription
                }
            }

            continuation.yield(
                .finished(
                    sessionId: sessionId,
                    finalSegments: finalSegments,
                    totalSegments: pipeline.nextSeq,
                    allWavFiles: pipeline.wavFiles,
                    writeErrorMessage: writeErrorMessage
                )
            )
        }
    }

    private func cancelRecording(sendCancelToEngine: Bool) {
        guard case let .recording(sessionId, _, pipeline) = sessionState else {
            return
        }
        let hadPendingStart = cancelPendingStartIfMatching(sessionId: sessionId)
        sessionState = .idle
        audioRecorder.cancel()

        let filesToDelete = audioQueue.sync { () -> [URL] in
            pipeline.isCancelled = true
            return pipeline.wavFiles
        }

        if sendCancelToEngine && !hadPendingStart {
            try? engineClient.send(.cancel(sessionId: sessionId))
        }
        deleteFiles(filesToDelete)
        cleanupTempFiles(for: sessionId)
        onAudioLevelChange?(0)
        recordOverlayEvent(.recordingCancelled)
        restoreIdleOrEngineState()
    }

    private nonisolated func enqueueAudioSamples(
        _ samples: [Int16],
        pipeline: RecordingPipeline,
        continuation: AsyncStream<AudioPipelineEvent>.Continuation
    ) {
        let level = OverlayAudioLevel.normalizedLevel(from: samples)
        let sessionId = pipeline.sessionId
        Task { @MainActor [weak self] in
            self?.handleAudioLevel(level, sessionId: sessionId)
        }

        audioQueue.async {
            guard !pipeline.isCancelled else { return }
            let closedSegments = pipeline.segmenter.push(samples: samples)
            guard !closedSegments.isEmpty else { return }

            for segment in closedSegments {
                guard !pipeline.isCancelled else { return }
                do {
                    let written = try pipeline.writeSegment(segment)
                    // audioQueue(直列) → AsyncStream(FIFO) により segment と finish の順序を厳密に保つ。
                    continuation.yield(
                        .segment(sessionId: pipeline.sessionId, seq: written.seq, url: written.url)
                    )
                } catch {
                    continuation.yield(
                        .runtimeError(
                            sessionId: pipeline.sessionId,
                            message: "一時WAVファイルの書き出しに失敗しました: \(error.localizedDescription)"
                        )
                    )
                    return
                }
            }
        }
    }

    private func sendSegmentIfActive(sessionId: String, seq: Int, url: URL) {
        trackedWavFiles[sessionId, default: []].append(url)
        let isMatchingActiveSession: Bool
        switch sessionState {
        case let .recording(activeId, _, _), let .finishing(activeId, _):
            isMatchingActiveSession = (activeId == sessionId)
        case .idle, .awaitingResult:
            isMatchingActiveSession = false
        }

        guard isMatchingActiveSession else {
            deleteFiles([url])
            return
        }
        do {
            try sendOrEnqueueForSession(
                .segment(sessionId: sessionId, seq: seq, wavPath: url.path),
                sessionId: sessionId
            )
        } catch {
            handleRecorderRuntimeError(error.localizedDescription, sessionId: sessionId)
        }
    }

    private func completeStopRecording(
        sessionId: String,
        finalSegments: [(seq: Int, url: URL)],
        totalSegments: Int,
        allWavFiles: [URL],
        writeErrorMessage: String?
    ) {
        trackedWavFiles[sessionId] = allWavFiles

        guard case let .finishing(activeId, target) = sessionState, activeId == sessionId else {
            cleanupTempFiles(for: sessionId)
            return
        }

        if let writeErrorMessage {
            let hadPendingStart = cancelPendingStartIfMatching(sessionId: sessionId)
            sessionState = .idle
            if !hadPendingStart {
                try? engineClient.send(.cancel(sessionId: sessionId))
            }
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.errorOccurred(message: "音声の保存に失敗しました"))
            restoreIdleOrEngineState()
            notifier.notify(title: "VoiceIME エラー", body: "一時WAVファイルの書き出しに失敗しました: \(writeErrorMessage)")
            return
        }

        guard engineClient.isReady else {
            _ = cancelPendingStartIfMatching(sessionId: sessionId)
            sessionState = .idle
            cleanupTempFiles(for: sessionId)
            applyOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
            return
        }

        // 発話区間が1つも確定しなかった（無音のみ等）場合は、空セッションを残さないようcancelして待機へ戻る。
        guard totalSegments > 0 else {
            let hadPendingStart = cancelPendingStartIfMatching(sessionId: sessionId)
            sessionState = .idle
            if !hadPendingStart {
                try? engineClient.send(.cancel(sessionId: sessionId))
            }
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.sessionFinishedEmpty)
            restoreIdleOrEngineState()
            return
        }

        do {
            for item in finalSegments {
                try sendOrEnqueueForSession(
                    .segment(sessionId: sessionId, seq: item.seq, wavPath: item.url.path),
                    sessionId: sessionId
                )
            }
            try sendOrEnqueueForSession(
                .finish(sessionId: sessionId, mode: .formatted),
                sessionId: sessionId
            )
            sessionState = .awaitingResult(sessionId: sessionId, target: target)
        } catch {
            _ = cancelPendingStartIfMatching(sessionId: sessionId)
            sessionState = .idle
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.errorOccurred(message: "認識エンジンへの送信に失敗しました"))
            restoreIdleOrEngineState()
            notifier.notify(title: "VoiceIME エラー", body: error.localizedDescription)
        }
    }

    private func handleRecorderRuntimeError(_ message: String, sessionId: String) {
        switch sessionState {
        case let .recording(activeId, _, _) where activeId == sessionId:
            cancelRecording(sendCancelToEngine: true)
            applyOverlayEvent(.errorOccurred(message: "録音エラーが発生しました"))
            notifier.notify(title: "VoiceIME 録音エラー", body: message)
        case let .finishing(activeId, _) where activeId == sessionId:
            let hadPendingStart = cancelPendingStartIfMatching(sessionId: sessionId)
            sessionState = .idle
            if !hadPendingStart {
                try? engineClient.send(.cancel(sessionId: sessionId))
            }
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.errorOccurred(message: "録音エラーが発生しました"))
            restoreIdleOrEngineState()
            notifier.notify(title: "VoiceIME 録音エラー", body: message)
        default:
            break
        }
    }

    /// `start` 送信前の場合は送信待ちキューへ積み、`start` が送られた直後にFIFO順でエンジンへ流す。
    private func sendOrEnqueueForSession(_ command: EngineCommand, sessionId: String) throws {
        if var pending = pendingStart, pending.sessionId == sessionId {
            pending.queuedCommands.append(command)
            pendingStart = pending
            return
        }
        try engineClient.send(command)
    }

    /// 非同期の画面文字読み取り完了（または時間切れ）を受けて `start` と保留中コマンドを順に送信する。
    private func finishPendingStart(
        sessionId: String,
        app: TargetAppInfo,
        screenText: String?
    ) {
        guard let pending = pendingStart, pending.sessionId == sessionId else {
            return
        }
        pendingStart = nil

        guard engineClient.isReady else {
            handlePendingStartSendFailure(EngineClientError.engineNotRunning, sessionId: sessionId)
            return
        }

        do {
            try engineClient.send(.start(sessionId: sessionId, app: app, screenText: screenText))
            for command in pending.queuedCommands {
                try engineClient.send(command)
            }
        } catch {
            handlePendingStartSendFailure(error, sessionId: sessionId)
        }
    }

    private func handlePendingStartSendFailure(_ error: Error, sessionId: String) {
        switch sessionState {
        case let .recording(activeId, _, _) where activeId == sessionId:
            cancelRecording(sendCancelToEngine: false)
            applyOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
        case let .finishing(activeId, _) where activeId == sessionId:
            sessionState = .idle
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
            restoreIdleOrEngineState()
        case let .awaitingResult(activeId, _) where activeId == sessionId:
            sessionState = .idle
            cleanupTempFiles(for: sessionId)
            recordOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
            restoreIdleOrEngineState()
        default:
            cleanupTempFiles(for: sessionId)
        }
        notifier.notify(title: "VoiceIME エラー", body: error.localizedDescription)
    }

    private func abortStartAfterSendFailure(
        _ error: Error,
        sessionId: String,
        pipeline: RecordingPipeline
    ) {
        sessionState = .idle
        audioRecorder.cancel()
        onAudioLevelChange?(0)
        let filesToDelete = audioQueue.sync { () -> [URL] in
            pipeline.isCancelled = true
            return pipeline.wavFiles
        }
        deleteFiles(filesToDelete)
        cleanupTempFiles(for: sessionId)
        recordOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
        restoreIdleOrEngineState()
        notifier.notify(title: "VoiceIME エラー", body: error.localizedDescription)
    }

    @discardableResult
    private func cancelPendingStartIfMatching(sessionId: String) -> Bool {
        guard let pending = pendingStart, pending.sessionId == sessionId else {
            return false
        }
        pendingStart = nil
        pending.task.cancel()
        return true
    }

    private func cancelAnyPendingStart() {
        guard let pending = pendingStart else { return }
        pendingStart = nil
        pending.task.cancel()
    }

    // MARK: - Engine Events

    private func wireCallbacks() {
        hotkeyMonitor.isRecordingProvider = { [weak self] in
            self?.sessionState.isRecording ?? false
        }
        hotkeyMonitor.onAction = { [weak self] action in
            self?.handleHotkeyAction(action)
        }

        engineClient.onStateChange = { [weak self] state in
            self?.handleEngineStateChange(state)
        }
        engineClient.onEvent = { [weak self] event in
            self?.handleEngineEvent(event)
        }
        engineClient.onUnexpectedExit = { [weak self] crash in
            self?.handleEngineCrash(crash)
        }
    }

    private func handleEngineStateChange(_ state: EngineLifecycleState) {
        switch state {
        case .stopped:
            updateUIState(
                iconState: .idle,
                statusText: "停止",
                hotkeyMode: uiState.hotkeyMode,
                lastResultText: uiState.lastResultText
            )
        case .starting:
            updateUIState(
                iconState: .processing,
                statusText: "認識エンジン起動中...",
                hotkeyMode: uiState.hotkeyMode,
                lastResultText: uiState.lastResultText
            )
        case .ready:
            recordOverlayEvent(.engineReady)
            if !sessionState.isBusy {
                updateUIState(
                    iconState: .idle,
                    statusText: "待機中",
                    hotkeyMode: uiState.hotkeyMode,
                    lastResultText: uiState.lastResultText
                )
            } else {
                refreshUIStateForOverlay()
            }
        case let .restarting(attempt):
            updateUIState(
                iconState: .error,
                statusText: "エンジン再起動中（\(attempt)回目）...",
                hotkeyMode: uiState.hotkeyMode,
                lastResultText: uiState.lastResultText
            )
        case let .failed(message):
            recordOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))
            updateUIState(
                iconState: .error,
                statusText: "エンジンエラー",
                hotkeyMode: uiState.hotkeyMode,
                lastResultText: uiState.lastResultText
            )
            notifier.notify(title: "VoiceIME エラー", body: message)
        }
    }

    private func handleEngineEvent(_ event: EngineEvent) {
        switch event {
        case .ready:
            break
        case let .partial(partial):
            handlePartialEvent(partial)
        case let .result(result):
            handleResultEvent(result)
        case let .error(errorEvent):
            handleErrorEvent(errorEvent)
        }
    }

    private func handlePartialEvent(_ partial: EnginePartialEvent) {
        guard case let .recording(activeId, _, _) = sessionState,
              activeId == partial.sessionId else {
            return
        }
        applyOverlayEvent(.partialReceived(seq: partial.seq, text: partial.text))
    }

    private func handleResultEvent(_ result: EngineResultEvent) {
        cleanupTempFiles(for: result.sessionId)

        guard case let .awaitingResult(expectedId, target) = sessionState,
              expectedId == result.sessionId else {
            return
        }
        sessionState = .idle

        let textToPaste: String
        if !result.text.isEmpty {
            textToPaste = result.text
        } else {
            textToPaste = result.rawText ?? ""
        }

        if !textToPaste.isEmpty {
            updateUIState(
                iconState: uiState.iconState,
                statusText: uiState.statusText,
                hotkeyMode: uiState.hotkeyMode,
                lastResultText: textToPaste
            )
        }

        Task { [weak self] in
            guard let self else { return }
            if !textToPaste.isEmpty {
                let outcome = await self.pasteController.paste(
                    text: textToPaste,
                    expectedTarget: target
                )
                switch outcome {
                case .pasted:
                    self.recordOverlayEvent(.pasteSucceeded)
                case let .copiedFallback(reason):
                    self.recordOverlayEvent(.pasteFallback(reason))
                    self.notifier.notify(title: "VoiceIME", body: reason.userMessage)
                case .skippedEmpty:
                    self.recordOverlayEvent(.sessionFinishedEmpty)
                }
            } else {
                self.recordOverlayEvent(.sessionFinishedEmpty)
            }
            self.restoreIdleOrEngineState()
        }
    }

    private func handleErrorEvent(_ errorEvent: EngineErrorEvent) {
        if let sessionId = errorEvent.sessionId {
            _ = cancelPendingStartIfMatching(sessionId: sessionId)
            cleanupTempFiles(for: sessionId)
        } else {
            cancelAnyPendingStart()
        }

        var targetForFallback: PasteTarget?
        switch sessionState {
        case let .awaitingResult(activeId, target)
            where errorEvent.sessionId == nil || activeId == errorEvent.sessionId:
            targetForFallback = target
            sessionState = .idle
        case let .finishing(activeId, target)
            where errorEvent.sessionId == nil || activeId == errorEvent.sessionId:
            targetForFallback = target
            sessionState = .idle
        case let .recording(activeId, target, _)
            where errorEvent.sessionId == nil || activeId == errorEvent.sessionId:
            targetForFallback = target
            cancelRecording(sendCancelToEngine: false)
        default:
            break
        }

        if let rawText = errorEvent.rawText, !rawText.isEmpty {
            updateUIState(
                iconState: uiState.iconState,
                statusText: uiState.statusText,
                hotkeyMode: uiState.hotkeyMode,
                lastResultText: rawText
            )
            Task { [weak self] in
                guard let self else { return }
                let outcome = await self.pasteController.paste(
                    text: rawText,
                    expectedTarget: targetForFallback
                )
                let note: String
                if case let .copiedFallback(reason) = outcome {
                    note = "\(errorEvent.message)（\(reason.userMessage)）"
                    self.recordOverlayEvent(.pasteFallback(reason))
                } else {
                    note = "\(errorEvent.message)（整形前の認識結果を貼り付けました）"
                    self.recordOverlayEvent(.errorOccurred(message: errorEvent.message))
                }
                self.notifier.notify(title: "VoiceIME エラー", body: note)
                self.restoreIdleOrEngineState()
            }
        } else {
            notifier.notify(title: "VoiceIME エラー", body: errorEvent.message)
            recordOverlayEvent(.errorOccurred(message: errorEvent.message))
            if engineClient.isReady {
                restoreIdleOrEngineState()
            } else {
                updateUIState(
                    iconState: .error,
                    statusText: "エラー",
                    hotkeyMode: uiState.hotkeyMode,
                    lastResultText: uiState.lastResultText
                )
            }
        }
    }

    private func handleEngineCrash(_ crash: EngineCrashInfo) {
        cancelAnyPendingStart()
        switch sessionState {
        case .recording:
            cancelRecording(sendCancelToEngine: false)
        case let .finishing(sessionId, _), let .awaitingResult(sessionId, _):
            sessionState = .idle
            cleanupTempFiles(for: sessionId)
        case .idle:
            break
        }
        applyOverlayEvent(.errorOccurred(message: "認識エンジンに接続できません", isEngineError: true))

        let detail = crash.stderrSummary.isEmpty
            ? "終了コード \(crash.exitStatus)"
            : "終了コード \(crash.exitStatus): \(crash.stderrSummary)"
        notifier.notify(
            title: "VoiceIME 認識エンジン再起動",
            body: "認識エンジンが異常終了したため再起動します（\(detail)）。"
        )
    }

    // MARK: - Helpers

    private func resolveScreenTextStatus(hasPermission: Bool) -> ScreenTextStatus {
        guard isScreenTextEnabled else {
            return .disabled
        }
        return hasPermission ? .enabled : .permissionMissing
    }

    private func notifyMissingPermissionsIfAny() {
        let status = permissionChecker.currentStatus()
        if let message = status.missingSummaryMessage() {
            notifier.notify(title: "VoiceIME 権限の確認", body: message)
        }
    }

    private func scheduleHotkeyRetryIfNeeded() {
        permissionRetryTask?.cancel()
        permissionRetryTask = Task { [weak self] in
            while let self, !Task.isCancelled, !self.hotkeyStarted {
                try? await Task.sleep(for: .seconds(3))
                guard !Task.isCancelled, !self.hotkeyStarted else { break }
                if self.permissionChecker.currentStatus().inputMonitoring {
                    self.hotkeyStarted = self.hotkeyMonitor.start()
                }
            }
        }
    }

    private func restoreIdleOrEngineState() {
        guard !sessionState.isBusy else { return }
        if engineClient.isReady {
            updateUIState(
                iconState: .idle,
                statusText: "待機中",
                hotkeyMode: uiState.hotkeyMode,
                lastResultText: uiState.lastResultText
            )
        } else {
            handleEngineStateChange(engineClient.state)
        }
    }

    private func updateUIState(
        iconState: AppIconState,
        statusText: String,
        hotkeyMode: HotkeyMode,
        screenTextStatus: ScreenTextStatus? = nil,
        lastResultText: String?
    ) {
        uiState = AppUIState(
            iconState: iconState,
            statusText: statusText,
            hotkeyMode: hotkeyMode,
            screenTextStatus: screenTextStatus ?? uiState.screenTextStatus,
            isOverlayEnabled: overlayStateMachine.isEnabled,
            overlayState: overlayStateMachine.displayState,
            lastResultText: lastResultText
        )
    }

    // MARK: - Overlay Helpers

    private func handleAudioLevel(_ level: Float, sessionId: String) {
        guard overlayStateMachine.isEnabled,
              case let .recording(activeId, _, _) = sessionState,
              activeId == sessionId else {
            return
        }
        onAudioLevelChange?(level)
    }

    private func recordOverlayEvent(_ event: OverlayEvent) {
        let transition = overlayStateMachine.apply(event)
        if transition.shouldCancelAutoHide {
            cancelOverlayAutoHideTask()
        }
        if let schedule = transition.autoHideSchedule {
            scheduleOverlayAutoHide(schedule)
        }
    }

    private func applyOverlayEvent(_ event: OverlayEvent) {
        recordOverlayEvent(event)
        refreshUIStateForOverlay()
    }

    private func refreshUIStateForOverlay() {
        updateUIState(
            iconState: uiState.iconState,
            statusText: uiState.statusText,
            hotkeyMode: uiState.hotkeyMode,
            lastResultText: uiState.lastResultText
        )
    }

    private func scheduleOverlayAutoHide(_ schedule: OverlayAutoHideSchedule) {
        cancelOverlayAutoHideTask()
        let token: UInt64
        let delay: Duration
        switch schedule {
        case let .done(t):
            token = t
            delay = doneAutoHideDelay
        case let .error(t):
            token = t
            delay = errorAutoHideDelay
        }
        overlayAutoHideTask = Task { [weak self] in
            if delay > .zero {
                try? await Task.sleep(for: delay)
            }
            guard let self, !Task.isCancelled else { return }
            self.applyOverlayEvent(.autoHideTimerFired(token: token))
        }
    }

    private func cancelOverlayAutoHideTask() {
        overlayAutoHideTask?.cancel()
        overlayAutoHideTask = nil
    }

    private func ensureTempDirectory() {
        try? FileManager.default.createDirectory(
            at: tempDirectory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
    }

    private func cleanupTempFiles(for sessionId: String) {
        guard let files = trackedWavFiles.removeValue(forKey: sessionId) else { return }
        deleteFiles(files)
    }

    private func cleanupAllTempFiles() {
        let all = trackedWavFiles.values.flatMap { $0 }
        trackedWavFiles.removeAll()
        deleteFiles(all)
    }

    private func deleteFiles(_ urls: [URL]) {
        for url in urls {
            try? FileManager.default.removeItem(at: url)
        }
    }
}
