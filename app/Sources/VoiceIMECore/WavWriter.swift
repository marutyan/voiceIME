import Foundation

/// WAV生成・書き出し時のエラー。
public enum WavWriterError: Error, LocalizedError, Equatable, Sendable {
    case sizeLimitExceeded

    public var errorDescription: String? {
        switch self {
        case .sizeLimitExceeded:
            return "録音データがWAV形式の上限サイズを超えています。"
        }
    }
}

/// 16kHz・モノラル・16bit PCMの標準RIFF WAVファイルを生成・保存するユーティリティ。
public enum WavWriter {
    public static let sampleRate: UInt32 = 16_000
    public static let channelCount: UInt16 = 1
    public static let bitsPerSample: UInt16 = 16

    /// サンプル配列から標準44バイトヘッダ付きの16kHzモノラル16bit PCM WAVデータを構築する。
    public static func makeWavData(samples: [Int16]) throws -> Data {
        let bytesPerSample = UInt32(bitsPerSample / 8)
        let dataByteCount64 = UInt64(samples.count) * UInt64(bytesPerSample)
        guard dataByteCount64 <= UInt64(UInt32.max - 36) else {
            throw WavWriterError.sizeLimitExceeded
        }

        let dataSize = UInt32(dataByteCount64)
        let riffChunkSize = 36 + dataSize
        let blockAlign = channelCount * (bitsPerSample / 8)
        let byteRate = sampleRate * UInt32(blockAlign)

        var data = Data()
        data.reserveCapacity(44 + Int(dataSize))

        data.append(contentsOf: [0x52, 0x49, 0x46, 0x46]) // "RIFF"
        appendLittleEndian(riffChunkSize, to: &data)
        data.append(contentsOf: [0x57, 0x41, 0x56, 0x45]) // "WAVE"

        data.append(contentsOf: [0x66, 0x6D, 0x74, 0x20]) // "fmt "
        appendLittleEndian(UInt32(16), to: &data)         // PCM fmtチャンク長
        appendLittleEndian(UInt16(1), to: &data)          // AudioFormat = 1 (PCM)
        appendLittleEndian(channelCount, to: &data)
        appendLittleEndian(sampleRate, to: &data)
        appendLittleEndian(byteRate, to: &data)
        appendLittleEndian(blockAlign, to: &data)
        appendLittleEndian(bitsPerSample, to: &data)

        data.append(contentsOf: [0x64, 0x61, 0x74, 0x61]) // "data"
        appendLittleEndian(dataSize, to: &data)

        for sample in samples {
            appendLittleEndian(UInt16(bitPattern: sample), to: &data)
        }
        return data
    }

    /// 16kHzモノラル16bit WAVを親ディレクトリ作成のうえ原子的に書き出す。
    public static func write(samples: [Int16], to url: URL) throws {
        let wavData = try makeWavData(samples: samples)
        let parent = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        try wavData.write(to: url, options: .atomic)
    }

    private static func appendLittleEndian<T: FixedWidthInteger>(_ value: T, to data: inout Data) {
        var le = value.littleEndian
        withUnsafeBytes(of: &le) { bytes in
            data.append(contentsOf: bytes)
        }
    }
}
