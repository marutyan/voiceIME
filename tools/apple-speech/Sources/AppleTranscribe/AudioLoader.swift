import AVFoundation
import AppleSpeechSupport
import Foundation
import Speech

/// 音声ファイルをメモリ上へ読み込み、SpeechAnalyzerが期待する形式の入力チャンク列へ変換する。
enum AudioLoader {
    /// 1チャンクあたりの標準フレーム数（16kHzで約1秒分）。巨大バッファによる制限を避けるため分割する。
    private static let defaultChunkDurationSeconds: Double = 1.0

    /// 指定した音声ファイルを全量読み込み、`targetFormat` へ揃えた `AnalyzerInput` 配列として返す。
    /// ファイルI/Oと形式変換を推論計測の前に完了させるために使う。
    static func loadAnalyzerInputs(from url: URL, targetFormat: AVAudioFormat) throws -> [AnalyzerInput] {
        let probeFile: AVAudioFile
        do {
            probeFile = try AVAudioFile(forReading: url)
        } catch {
            throw CLIError.runtime("音声ファイルを開けませんでした (\(url.path)): \(error.localizedDescription)")
        }

        guard probeFile.length > 0 else {
            return []
        }

        let fileFormat = probeFile.fileFormat
        let canReadDirectly =
            fileFormat.sampleRate == targetFormat.sampleRate &&
            fileFormat.channelCount == targetFormat.channelCount

        if canReadDirectly,
           let directFile = try? AVAudioFile(
               forReading: url,
               commonFormat: targetFormat.commonFormat,
               interleaved: targetFormat.isInterleaved
           ),
           directFile.processingFormat == targetFormat {
            return try readDirectly(from: directFile, targetFormat: targetFormat)
        }
        return try readAndConvert(from: probeFile, targetFormat: targetFormat)
    }

    /// フォーマットが完全一致する場合に、`AVAudioFile` から変換なしで直接 `targetFormat` へ読み込む。
    private static func readDirectly(from audioFile: AVAudioFile, targetFormat: AVAudioFormat) throws -> [AnalyzerInput] {
        let chunkFrames = AVAudioFrameCount(max(4096, Int((targetFormat.sampleRate * defaultChunkDurationSeconds).rounded())))
        var inputs: [AnalyzerInput] = []

        while audioFile.framePosition < audioFile.length {
            let remaining = AVAudioFrameCount(min(Int64(chunkFrames), audioFile.length - audioFile.framePosition))
            guard remaining > 0 else { break }
            guard let buffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: remaining) else {
                throw CLIError.runtime("音声バッファの確保に失敗しました。")
            }
            try audioFile.read(into: buffer, frameCount: remaining)
            if buffer.frameLength == 0 {
                break
            }
            inputs.append(AnalyzerInput(buffer: buffer))
        }
        return inputs
    }

    /// サンプルレートまたはチャンネル数が異なる場合に、`AVAudioConverter` で変換しながら全フレームを読み込む。
    private static func readAndConvert(from audioFile: AVAudioFile, targetFormat: AVAudioFormat) throws -> [AnalyzerInput] {
        let sourceFormat = audioFile.processingFormat
        guard let converter = AVAudioConverter(from: sourceFormat, to: targetFormat) else {
            throw CLIError.runtime("音声形式の変換器を作成できませんでした (\(sourceFormat) -> \(targetFormat))。")
        }

        let sourceChunkFrames = AVAudioFrameCount(max(4096, Int((sourceFormat.sampleRate * defaultChunkDurationSeconds).rounded())))
        let sampleRateRatio = targetFormat.sampleRate / sourceFormat.sampleRate
        let outputChunkCapacity = AVAudioFrameCount(ceil(Double(sourceChunkFrames) * sampleRateRatio)) + 1024

        var inputs: [AnalyzerInput] = []

        while audioFile.framePosition < audioFile.length {
            let remaining = AVAudioFrameCount(min(Int64(sourceChunkFrames), audioFile.length - audioFile.framePosition))
            guard remaining > 0 else { break }
            guard let inputBuffer = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: remaining) else {
                throw CLIError.runtime("入力音声バッファの確保に失敗しました。")
            }
            try audioFile.read(into: inputBuffer, frameCount: remaining)
            if inputBuffer.frameLength == 0 {
                break
            }

            // チャンク変換中はリサンプラのフィルタ状態を保つため、1回渡したら `.noDataNow` を返す。
            var provided = false
            while true {
                guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outputChunkCapacity) else {
                    throw CLIError.runtime("変換後音声バッファの確保に失敗しました。")
                }
                var convertError: NSError?
                let status = converter.convert(to: outputBuffer, error: &convertError) { _, outStatus in
                    if provided {
                        outStatus.pointee = .noDataNow
                        return nil
                    }
                    provided = true
                    outStatus.pointee = .haveData
                    return inputBuffer
                }
                if let convertError {
                    throw CLIError.runtime("音声形式の変換に失敗しました: \(convertError.localizedDescription)")
                }
                if outputBuffer.frameLength > 0 {
                    inputs.append(AnalyzerInput(buffer: outputBuffer))
                }
                if status == .inputRanDry || status == .endOfStream || status == .error {
                    break
                }
            }
        }

        // ファイル終端に達した後、リサンプラ内部に残った末尾フレームを `.endOfStream` で掃き出す。
        while true {
            guard let tailBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outputChunkCapacity) else {
                throw CLIError.runtime("終端音声バッファの確保に失敗しました。")
            }
            var convertError: NSError?
            let status = converter.convert(to: tailBuffer, error: &convertError) { _, outStatus in
                outStatus.pointee = .endOfStream
                return nil
            }
            if let convertError {
                throw CLIError.runtime("音声形式の終端変換に失敗しました: \(convertError.localizedDescription)")
            }
            if tailBuffer.frameLength > 0 {
                inputs.append(AnalyzerInput(buffer: tailBuffer))
            }
            if status == .endOfStream || status == .error || tailBuffer.frameLength == 0 {
                break
            }
        }

        return inputs
    }
}
