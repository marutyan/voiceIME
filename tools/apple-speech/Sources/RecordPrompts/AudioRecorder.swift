import AVFoundation
import AppleSpeechSupport
import Foundation
import os

/// 録音スレッドとメインスレッドの間で変換器と蓄積サンプルを安全に共有するための状態箱。
private final class RecorderBufferState: @unchecked Sendable {
    let targetFormat: AVAudioFormat
    let converter: AVAudioConverter
    var samples: [Int16] = []
    var conversionError: String?

    init(targetFormat: AVAudioFormat, converter: AVAudioConverter) {
        self.targetFormat = targetFormat
        self.converter = converter
    }

    /// ハードウェア入力バッファを16kHzモノラルInt16へ変換して末尾へ追加する。
    func append(inputBuffer: AVAudioPCMBuffer) {
        guard inputBuffer.frameLength > 0 else { return }
        let ratio = targetFormat.sampleRate / inputBuffer.format.sampleRate
        let outCapacity = AVAudioFrameCount(ceil(Double(inputBuffer.frameLength) * ratio)) + 1024

        var provided = false
        while true {
            guard let outBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outCapacity) else {
                conversionError = "録音変換用バッファの確保に失敗しました。"
                return
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
                return
            }
            appendInt16(from: outBuffer)
            if status == .inputRanDry || status == .endOfStream || status == .error {
                break
            }
        }
    }

    /// 録音終了時にリサンプラ内部へ残った末尾フレームを掃き出す。
    func flush() {
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
            appendInt16(from: outBuffer)
            if status == .endOfStream || status == .error || outBuffer.frameLength == 0 {
                break
            }
        }
    }

    private func appendInt16(from buffer: AVAudioPCMBuffer) {
        let count = Int(buffer.frameLength)
        guard count > 0, let channelData = buffer.int16ChannelData else { return }
        let ptr = UnsafeBufferPointer(start: channelData[0], count: count)
        samples.append(contentsOf: ptr)
    }
}

/// マイク権限の確認と、`AVAudioEngine` による16kHzモノラル16bit PCM録音を行うクラス。
final class MicrophoneRecorder {
    private var engine: AVAudioEngine?
    private var lockedState: OSAllocatedUnfairLock<RecorderBufferState>?

    /// マイクの利用権限を確認し、未決定であればシステムダイアログで許可を求める。
    static func ensureMicrophonePermission() async throws {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .audio)
            guard granted else {
                throw CLIError.runtime(Self.permissionDeniedMessage)
            }
        case .denied, .restricted:
            throw CLIError.runtime(Self.permissionDeniedMessage)
        @unknown default:
            throw CLIError.runtime("マイク権限の状態を確認できませんでした。")
        }
    }

    private static let permissionDeniedMessage = """
    マイクへのアクセスが許可されていません。
    「システム設定 > プライバシーとセキュリティ > マイク」で、使用中のターミナルアプリ（Terminal / iTerm2 等）を許可してから再実行してください。
    """

    /// ハードウェア入力フォーマットでタップを張り、16kHzモノラル16bit PCMへ変換しながら録音を開始する。
    func start() throws {
        cancel()

        let engine = AVAudioEngine()
        let inputNode = engine.inputNode
        let hwFormat = inputNode.outputFormat(forBus: 0)
        guard hwFormat.sampleRate > 0, hwFormat.channelCount > 0 else {
            throw CLIError.runtime("有効なマイク入力デバイスが見つかりません（サンプルレートまたはチャンネル数が0です）。")
        }

        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: Double(WavWriter.sampleRate),
            channels: AVAudioChannelCount(WavWriter.channelCount),
            interleaved: true
        ) else {
            throw CLIError.runtime("16kHzモノラル16bitフォーマットの初期化に失敗しました。")
        }

        guard let converter = AVAudioConverter(from: hwFormat, to: targetFormat) else {
            throw CLIError.runtime("マイク入力形式（\(Int(hwFormat.sampleRate))Hz, \(hwFormat.channelCount)ch）から16kHzモノラルへの変換器を作成できません。")
        }

        let stateLock = OSAllocatedUnfairLock(initialState: RecorderBufferState(targetFormat: targetFormat, converter: converter))

        // CoreAudioのリアルタイムスレッドから呼ばれるため、ディスクI/Oを行わずメモリ上へ変換・蓄積する。
        // バッファはこの同期ロック内でのみ消費され外へ逃さないため `withLockUnchecked` を使う。
        inputNode.installTap(onBus: 0, bufferSize: 4096, format: hwFormat) { buffer, _ in
            stateLock.withLockUnchecked { state in
                state.append(inputBuffer: buffer)
            }
        }

        engine.prepare()
        do {
            try engine.start()
        } catch {
            inputNode.removeTap(onBus: 0)
            throw CLIError.runtime("録音の開始に失敗しました: \(error.localizedDescription)")
        }

        self.engine = engine
        self.lockedState = stateLock
    }

    /// 録音を停止してリサンプラ末尾を掃き出し、録音済みの16kHzモノラルInt16サンプル列を返す。
    func stop() throws -> [Int16] {
        guard let engine, let lockedState else {
            return []
        }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        self.engine = nil
        self.lockedState = nil

        let (samples, errorMessage) = lockedState.withLock { state -> ([Int16], String?) in
            state.flush()
            return (state.samples, state.conversionError)
        }
        if let errorMessage {
            throw CLIError.runtime("録音中の音声変換でエラーが発生しました: \(errorMessage)")
        }
        return samples
    }

    /// 録音中のエンジンを安全に停止し、取得途中のデータを破棄する。
    func cancel() {
        if let engine {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        self.engine = nil
        self.lockedState = nil
    }
}
