import Foundation

/// 録音音声の無音区切り・上限分割の判定パラメータ。
public struct SegmenterConfig: Sendable, Equatable {
    /// 音声のサンプルレート（Hz）。
    public let sampleRate: Int
    /// 1フレームの長さ（ms）。
    public let frameDurationMs: Int
    /// 録音冒頭で背景雑音を測定する期間（ms）。
    public let calibrationDurationMs: Int
    /// 無音が連続して区間を確定するまでの時間（ms）。
    public let silenceCloseMs: Int
    /// 1区間の最大長（ms）。達したら直近の最も静かな位置で分割する。
    public let maxIntervalMs: Int
    /// 上限分割時に最も静かなフレームを探す直近の探索幅（ms）。
    public let cutSearchWindowMs: Int
    /// 無音で区間を閉じるときに最後の発話の後ろへ残す余白（ms）。
    public let trailingSilenceMs: Int
    /// 背景雑音の何倍以上を発話とみなすかの倍率。
    public let speechToNoiseRatio: Float
    /// 静かな部屋でも発話と判定する最小RMSしきい値。
    public let minSpeechRMS: Float
    /// 背景雑音として学習するRMSの上限。話し声や咳を雑音と誤学習しないために設ける。
    public let maxCalibrationNoiseRMS: Float
    /// クリック雑音で誤開始しないために必要な連続発話フレーム数。
    public let minSpeechFrames: Int
    /// 冒頭から話し続けた場合などに使う背景雑音の初期値。
    public let initialNoiseFloor: Float
    /// キャリブレーション後の非発話フレームでの背景雑音追従係数（EMA）。
    public let noiseFloorAdaptationRate: Float

    public init(
        sampleRate: Int = 16_000,
        frameDurationMs: Int = 20,
        calibrationDurationMs: Int = 300,
        silenceCloseMs: Int = 600,
        maxIntervalMs: Int = 20_000,
        cutSearchWindowMs: Int = 5_000,
        trailingSilenceMs: Int = 200,
        speechToNoiseRatio: Float = 3.0,
        minSpeechRMS: Float = 0.006,
        maxCalibrationNoiseRMS: Float = 0.02,
        minSpeechFrames: Int = 3,
        initialNoiseFloor: Float = 0.002,
        noiseFloorAdaptationRate: Float = 0.05
    ) {
        self.sampleRate = sampleRate
        self.frameDurationMs = frameDurationMs
        self.calibrationDurationMs = calibrationDurationMs
        self.silenceCloseMs = silenceCloseMs
        self.maxIntervalMs = maxIntervalMs
        self.cutSearchWindowMs = cutSearchWindowMs
        self.trailingSilenceMs = trailingSilenceMs
        self.speechToNoiseRatio = speechToNoiseRatio
        self.minSpeechRMS = minSpeechRMS
        self.maxCalibrationNoiseRMS = maxCalibrationNoiseRMS
        self.minSpeechFrames = minSpeechFrames
        self.initialNoiseFloor = initialNoiseFloor
        self.noiseFloorAdaptationRate = noiseFloorAdaptationRate
    }

    public static let `default` = SegmenterConfig()

    /// 1フレーム当たりのサンプル数。
    public var frameSamples: Int {
        max(1, (sampleRate * frameDurationMs) / 1000)
    }

    /// キャリブレーション期間のフレーム数。
    public var calibrationFrames: Int {
        max(0, calibrationDurationMs / frameDurationMs)
    }

    /// 無音で閉じる連続フレーム数。
    public var silenceCloseFrames: Int {
        max(1, silenceCloseMs / frameDurationMs)
    }

    /// 1区間の最大フレーム数。
    public var maxIntervalFrames: Int {
        max(1, maxIntervalMs / frameDurationMs)
    }

    /// 上限分割時の探索フレーム数。
    public var cutSearchFrames: Int {
        max(1, cutSearchWindowMs / frameDurationMs)
    }

    /// 無音クローズ後に残す末尾余白フレーム数。
    public var trailingSilenceFrames: Int {
        max(0, trailingSilenceMs / frameDurationMs)
    }
}

/// 確定した1区間分の音声データとフレーム境界。
public struct AudioSegment: Sendable, Equatable {
    /// 16kHzモノラル16bit PCMサンプル列。
    public let samples: [Int16]
    /// 録音先頭からの開始フレーム番号（0始まり・含む）。
    public let startFrame: Int
    /// 録音先頭からの終了フレーム番号（含まない）。端数サンプルを含む末尾区間では切り捨てフレーム数になる。
    public let endFrame: Int

    public init(samples: [Int16], startFrame: Int, endFrame: Int) {
        self.samples = samples
        self.startFrame = startFrame
        self.endFrame = endFrame
    }
}

/// 16kHzモノラル音声を背景雑音測定・無音検出・上限分割で区間単位に切り出すステートマシン。
public struct AudioSegmenter: Sendable {
    private struct BufferedFrame: Sendable {
        let index: Int
        let samples: [Int16]
        let rms: Float
    }

    public let config: SegmenterConfig

    /// 現在の推定背景雑音RMS。
    public private(set) var noiseFloor: Float
    /// 現在の発話判定しきい値RMS。
    public var threshold: Float {
        max(noiseFloor * config.speechToNoiseRatio, config.minSpeechRMS)
    }
    /// 現在開いている発話区間があるか。
    public var hasOpenSegment: Bool {
        !openSamples.isEmpty
    }

    private var remainder: [Int16] = []
    private var nextFrameIndex: Int = 0
    private var isCalibrated: Bool
    private var calibrationBuffer: [BufferedFrame] = []
    private var calibrationNoiseRMS: [Float] = []

    private var lookahead: [BufferedFrame] = []

    private var openSamples: [Int16] = []
    private var openFrameRMS: [Float] = []
    private var openStartFrame: Int = 0
    private var openFrameCount: Int = 0
    /// 開いている区間内で最後に発話と判定されたフレームまでのフレーム数。
    private var lastSpeechFrameCount: Int = 0
    private var silenceRunFrames: Int = 0

    public init(config: SegmenterConfig = .default) {
        self.config = config
        self.noiseFloor = config.initialNoiseFloor
        self.isCalibrated = (config.calibrationFrames == 0)
    }

    /// Int16サンプル列の正規化RMS（0.0〜1.0）を計算する。
    public static func rms(of samples: [Int16]) -> Float {
        guard !samples.isEmpty else { return 0 }
        var sumSquares: Double = 0
        for sample in samples {
            let normalized = Double(sample) / 32768.0
            sumSquares += normalized * normalized
        }
        return Float(sqrt(sumSquares / Double(samples.count)))
    }

    /// 新しいPCMサンプル列を入力し、この呼び出しで確定した区間をすべて返す。
    public mutating func push(samples: [Int16]) -> [AudioSegment] {
        guard !samples.isEmpty else { return [] }
        let frameSize = config.frameSamples
        var combined: [Int16]
        if remainder.isEmpty {
            combined = samples
        } else {
            combined = remainder
            combined.reserveCapacity(remainder.count + samples.count)
            combined.append(contentsOf: samples)
            remainder.removeAll(keepingCapacity: true)
        }

        var closed: [AudioSegment] = []
        var offset = 0
        while offset + frameSize <= combined.count {
            let frameSlice = Array(combined[offset ..< (offset + frameSize)])
            let frameRMS = Self.rms(of: frameSlice)
            closed.append(contentsOf: ingestFrame(samples: frameSlice, rms: frameRMS))
            offset += frameSize
        }

        if offset < combined.count {
            remainder.append(contentsOf: combined[offset...])
        }
        return closed
    }

    /// テストや音量シミュレーション向けに、各フレームのRMS列を与えて区間判定を行う。
    public mutating func pushFrameLevels(_ rmsLevels: [Float]) -> [AudioSegment] {
        let frameSize = config.frameSamples
        var closed: [AudioSegment] = []
        for level in rmsLevels {
            let clamped = max(0, min(1, level))
            let amplitude = Int16(clamping: Int(round(clamped * 32767.0)))
            let frame = [Int16](repeating: amplitude, count: frameSize)
            closed.append(contentsOf: ingestFrame(samples: frame, rms: clamped))
        }
        return closed
    }

    /// 録音終了時に呼び出し、未確定の発話区間が残っていれば端数サンプルごと返して状態を初期化する。
    public mutating func finish() -> AudioSegment? {
        var pendingClosed: [AudioSegment] = []
        if !isCalibrated {
            pendingClosed = finalizeCalibration()
        }

        // もしキャリブレーション確定だけで区間が閉じた（極めて特殊な設定）場合、最後の区間以外は無視されないよう
        // 現実的な設定では起きないが、残った開区間を優先して返す。
        if openSamples.isEmpty && lookahead.count >= config.minSpeechFrames {
            openFromLookahead()
        }

        let leftover = remainder
        remainder.removeAll(keepingCapacity: false)
        lookahead.removeAll(keepingCapacity: false)

        if !openSamples.isEmpty {
            if !leftover.isEmpty {
                openSamples.append(contentsOf: leftover)
            }
            let segment = AudioSegment(
                samples: openSamples,
                startFrame: openStartFrame,
                endFrame: openStartFrame + openFrameCount
            )
            resetOpenSegment()
            return segment
        }

        resetOpenSegment()
        return pendingClosed.last
    }

    /// 1フレーム分のサンプルとRMSを取り込み、キャリブレーションまたは区間処理へ進める。
    private mutating func ingestFrame(samples: [Int16], rms: Float) -> [AudioSegment] {
        let frame = BufferedFrame(index: nextFrameIndex, samples: samples, rms: rms)
        nextFrameIndex += 1

        if !isCalibrated {
            calibrationBuffer.append(frame)
            if rms < config.maxCalibrationNoiseRMS {
                calibrationNoiseRMS.append(rms)
            }
            if calibrationBuffer.count >= config.calibrationFrames {
                return finalizeCalibration()
            }
            return []
        }

        if let closed = processCalibratedFrame(frame, adaptNoiseFloor: true) {
            return [closed]
        }
        return []
    }

    /// 冒頭キャリブレーション期間で収集したフレームから背景雑音の中央値を確定し、蓄積フレームを再評価する。
    private mutating func finalizeCalibration() -> [AudioSegment] {
        isCalibrated = true
        if !calibrationNoiseRMS.isEmpty {
            let sorted = calibrationNoiseRMS.sorted()
            let mid = sorted.count / 2
            if sorted.count % 2 == 1 {
                noiseFloor = sorted[mid]
            } else {
                noiseFloor = (sorted[mid - 1] + sorted[mid]) * 0.5
            }
        }

        let buffered = calibrationBuffer
        calibrationBuffer.removeAll(keepingCapacity: false)
        calibrationNoiseRMS.removeAll(keepingCapacity: false)

        var closed: [AudioSegment] = []
        for frame in buffered {
            if let segment = processCalibratedFrame(frame, adaptNoiseFloor: false) {
                closed.append(segment)
            }
        }
        return closed
    }

    /// キャリブレーション完了後の1フレームを処理し、区間が確定すれば返す。
    private mutating func processCalibratedFrame(
        _ frame: BufferedFrame,
        adaptNoiseFloor: Bool
    ) -> AudioSegment? {
        let currentThreshold = threshold
        let isSpeech = frame.rms >= currentThreshold

        if adaptNoiseFloor && !isSpeech && frame.rms < config.maxCalibrationNoiseRMS {
            noiseFloor += (frame.rms - noiseFloor) * config.noiseFloorAdaptationRate
        }

        if openSamples.isEmpty {
            return detectSegmentStart(frame: frame, isSpeech: isSpeech)
        }
        return growOpenSegment(frame: frame, isSpeech: isSpeech)
    }

    private mutating func detectSegmentStart(frame: BufferedFrame, isSpeech: Bool) -> AudioSegment? {
        guard isSpeech else {
            lookahead.removeAll(keepingCapacity: true)
            return nil
        }

        lookahead.append(frame)
        guard lookahead.count >= config.minSpeechFrames else {
            return nil
        }

        openFromLookahead()
        // 最小発話フレーム数が上限以上という極端な設定に対する防御。
        if openFrameCount >= config.maxIntervalFrames {
            return cutAtQuietestFrame()
        }
        return nil
    }

    private mutating func openFromLookahead() {
        guard let first = lookahead.first else { return }
        openStartFrame = first.index
        openFrameCount = 0
        openSamples.removeAll(keepingCapacity: true)
        openFrameRMS.removeAll(keepingCapacity: true)

        for item in lookahead {
            openSamples.append(contentsOf: item.samples)
            openFrameRMS.append(item.rms)
            openFrameCount += 1
        }
        lastSpeechFrameCount = openFrameCount
        silenceRunFrames = 0
        lookahead.removeAll(keepingCapacity: true)
    }

    private mutating func growOpenSegment(frame: BufferedFrame, isSpeech: Bool) -> AudioSegment? {
        openSamples.append(contentsOf: frame.samples)
        openFrameRMS.append(frame.rms)
        openFrameCount += 1

        // 話し続けている最中でも20秒上限で必ず分割できるよう、発話継続判定より先に上限を見る。
        if openFrameCount >= config.maxIntervalFrames {
            return cutAtQuietestFrame()
        }

        if isSpeech {
            lastSpeechFrameCount = openFrameCount
            silenceRunFrames = 0
            return nil
        }

        silenceRunFrames += 1
        if silenceRunFrames >= config.silenceCloseFrames {
            return closeAfterSilence()
        }
        return nil
    }

    /// 最後の発話の後ろに一定の余白だけ残して区間を閉じ、それ以降の無音は破棄する。
    private mutating func closeAfterSilence() -> AudioSegment {
        let keepFrames = min(lastSpeechFrameCount + config.trailingSilenceFrames, openFrameCount)
        let keepSampleCount = min(keepFrames * config.frameSamples, openSamples.count)
        let segment = AudioSegment(
            samples: Array(openSamples[0 ..< keepSampleCount]),
            startFrame: openStartFrame,
            endFrame: openStartFrame + keepFrames
        )
        resetOpenSegment()
        return segment
    }

    /// 上限到達時に直近探索窓の中で最も静かなフレーム直後で分割し、後半を次の区間として残す。
    private mutating func cutAtQuietestFrame() -> AudioSegment {
        let totalFrames = openFrameCount
        guard totalFrames > 1 else {
            let segment = AudioSegment(
                samples: openSamples,
                startFrame: openStartFrame,
                endFrame: openStartFrame + totalFrames
            )
            resetOpenSegment()
            return segment
        }

        let searchStart = max(0, totalFrames - config.cutSearchFrames)
        var quietestIndex = searchStart
        for idx in searchStart ..< totalFrames {
            // 同値の場合は後ろ側を選び、静かな区間を前のセグメント末尾へ寄せる。
            if openFrameRMS[idx] <= openFrameRMS[quietestIndex] {
                quietestIndex = idx
            }
        }

        // 前後どちらの区間も空にならないよう 1 ... (totalFrames - 1) に収める。
        let cutFrames = min(max(1, quietestIndex + 1), totalFrames - 1)
        let cutSampleCount = cutFrames * config.frameSamples

        let emitted = AudioSegment(
            samples: Array(openSamples[0 ..< cutSampleCount]),
            startFrame: openStartFrame,
            endFrame: openStartFrame + cutFrames
        )

        openSamples = Array(openSamples[cutSampleCount...])
        openFrameRMS = Array(openFrameRMS[cutFrames...])
        openStartFrame += cutFrames
        openFrameCount = totalFrames - cutFrames
        lastSpeechFrameCount = openFrameCount
        silenceRunFrames = 0
        return emitted
    }

    private mutating func resetOpenSegment() {
        openSamples.removeAll(keepingCapacity: true)
        openFrameRMS.removeAll(keepingCapacity: true)
        openStartFrame = 0
        openFrameCount = 0
        lastSpeechFrameCount = 0
        silenceRunFrames = 0
    }
}
