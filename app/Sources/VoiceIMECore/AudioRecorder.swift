import AVFoundation
import Foundation
import os

/// マイク録音・形式変換に関わるエラー。
public enum AudioRecorderError: Error, LocalizedError, Equatable, Sendable {
    case invalidInputFormat
    case formatInitializationFailed
    case converterCreationFailed(sampleRate: Int, channels: Int)
    case startFailed(String)
    case conversionFailed(String)

    public var errorDescription: String? {
        switch self {
        case .invalidInputFormat:
            return "有効なマイク入力デバイスが見つかりません。"
        case .formatInitializationFailed:
            return "16kHzモノラル16bitフォーマットの初期化に失敗しました。"
        case let .converterCreationFailed(sampleRate, channels):
            return "マイク入力形式（\(sampleRate)Hz, \(channels)ch）から16kHzモノラルへの変換器を作成できません。"
        case let .startFailed(detail):
            return "録音の開始に失敗しました: \(detail)"
        case let .conversionFailed(detail):
            return "録音中の音声変換に失敗しました: \(detail)"
        }
    }
}

/// 録音機能の抽象インターフェース。実機では`MicrophoneAudioRecorder`を使い、テストでは合成音声を流す。
public protocol AudioRecorderProtocol: AnyObject {
    /// 録音を開始し、16kHzモノラル16bit PCMチャンクが届くたびに `onSamples` を呼ぶ。
    func start(
        onSamples: @escaping @Sendable ([Int16]) -> Void,
        onError: @escaping @Sendable (String) -> Void
    ) throws
    /// 録音を停止し、リサンプラ末尾に残ったサンプル列を返す。
    func stop() throws -> [Int16]
    /// 録音を即時停止し、残データを破棄する。
    func cancel()
}

/// CoreAudioの録音スレッドとメインスレッドの間で変換器の状態を安全に保護する箱。
private final class StreamingConverterState: @unchecked Sendable {
    let targetFormat: AVAudioFormat
    let converter: AVAudioConverter
    var conversionError: String?

    init(targetFormat: AVAudioFormat, converter: AVAudioConverter) {
        self.targetFormat = targetFormat
        self.converter = converter
    }

    /// 入力PCMバッファを16kHzモノラルInt16配列へ変換して返す。
    func convert(inputBuffer: AVAudioPCMBuffer) -> [Int16] {
        guard inputBuffer.frameLength > 0 else { return [] }
        let ratio = targetFormat.sampleRate / inputBuffer.format.sampleRate
        let outCapacity = AVAudioFrameCount(ceil(Double(inputBuffer.frameLength) * ratio)) + 1024

        var result: [Int16] = []
        var provided = false
        while true {
            guard let outBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outCapacity) else {
                conversionError = "録音変換用バッファの確保に失敗しました。"
                return result
            }
            var error: NSError?
            let status = converter.convert(to: outBuffer, error: &error) { _, outStatus in
                if provided {
                    outStatus.pointee = .noDataNow
                    return nil
                }
                provided = true
                outStatus.pointee = .haveData
                return inputBuffer
            }
            if let error {
                conversionError = error.localizedDescription
                return result
            }
            appendInt16(from: outBuffer, to: &result)
            if status == .inputRanDry || status == .endOfStream || status == .error {
                break
            }
        }
        return result
    }

    /// 録音停止時にリサンプラ内部へ残っている末尾フレームを掃き出す。
    func flush() -> [Int16] {
        var result: [Int16] = []
        let outCapacity: AVAudioFrameCount = 2048
        while true {
            guard let outBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outCapacity) else {
                break
            }
            var error: NSError?
            let status = converter.convert(to: outBuffer, error: &error) { _, outStatus in
                outStatus.pointee = .endOfStream
                return nil
            }
            if error != nil {
                break
            }
            appendInt16(from: outBuffer, to: &result)
            if status == .endOfStream || status == .error || outBuffer.frameLength == 0 {
                break
            }
        }
        return result
    }

    private func appendInt16(from buffer: AVAudioPCMBuffer, to output: inout [Int16]) {
        let count = Int(buffer.frameLength)
        guard count > 0, let channelData = buffer.int16ChannelData else { return }
        let ptr = UnsafeBufferPointer(start: channelData[0], count: count)
        output.append(contentsOf: ptr)
    }
}

/// `AVAudioEngine` でマイク入力を取り込み、16kHzモノラル16bit PCMへ逐次変換して届ける録音器。
public final class MicrophoneAudioRecorder: AudioRecorderProtocol {
    private var engine: AVAudioEngine?
    private var converterLock: OSAllocatedUnfairLock<StreamingConverterState>?
    private var configChangeObserver: NSObjectProtocol?

    public init() {}

    deinit {
        cancel()
    }

    public func start(
        onSamples: @escaping @Sendable ([Int16]) -> Void,
        onError: @escaping @Sendable (String) -> Void
    ) throws {
        cancel()

        let engine = AVAudioEngine()
        let inputNode = engine.inputNode
        let hwFormat = inputNode.outputFormat(forBus: 0)
        guard hwFormat.sampleRate > 0, hwFormat.channelCount > 0 else {
            throw AudioRecorderError.invalidInputFormat
        }

        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: Double(WavWriter.sampleRate),
            channels: AVAudioChannelCount(WavWriter.channelCount),
            interleaved: true
        ) else {
            throw AudioRecorderError.formatInitializationFailed
        }

        guard let converter = AVAudioConverter(from: hwFormat, to: targetFormat) else {
            throw AudioRecorderError.converterCreationFailed(
                sampleRate: Int(hwFormat.sampleRate),
                channels: Int(hwFormat.channelCount)
            )
        }

        let lock = OSAllocatedUnfairLock(
            initialState: StreamingConverterState(targetFormat: targetFormat, converter: converter)
        )

        // CoreAudioリアルタイムスレッドではディスクI/Oを行わず、16kHz Int16変換結果だけをコールバックへ渡す。
        inputNode.installTap(onBus: 0, bufferSize: 2048, format: hwFormat) { buffer, _ in
            let (samples, errorMessage) = lock.withLockUnchecked { state -> ([Int16], String?) in
                let converted = state.convert(inputBuffer: buffer)
                let err = state.conversionError
                state.conversionError = nil
                return (converted, err)
            }
            if let errorMessage {
                onError(AudioRecorderError.conversionFailed(errorMessage).localizedDescription)
            }
            if !samples.isEmpty {
                onSamples(samples)
            }
        }

        configChangeObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: engine,
            queue: nil
        ) { _ in
            onError("オーディオ入力デバイスの構成が変更されました。もう一度録音してください。")
        }

        engine.prepare()
        do {
            try engine.start()
        } catch {
            inputNode.removeTap(onBus: 0)
            if let observer = configChangeObserver {
                NotificationCenter.default.removeObserver(observer)
                configChangeObserver = nil
            }
            throw AudioRecorderError.startFailed(error.localizedDescription)
        }

        self.engine = engine
        self.converterLock = lock
    }

    public func stop() throws -> [Int16] {
        guard let engine, let converterLock else {
            return []
        }
        removeConfigObserver()
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        self.engine = nil
        self.converterLock = nil

        let (tail, errorMessage) = converterLock.withLock { state -> ([Int16], String?) in
            let flushed = state.flush()
            return (flushed, state.conversionError)
        }
        if let errorMessage {
            throw AudioRecorderError.conversionFailed(errorMessage)
        }
        return tail
    }

    public func cancel() {
        removeConfigObserver()
        if let engine {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        self.engine = nil
        self.converterLock = nil
    }

    private func removeConfigObserver() {
        if let observer = configChangeObserver {
            NotificationCenter.default.removeObserver(observer)
            configChangeObserver = nil
        }
    }
}
