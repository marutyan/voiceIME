import AVFoundation
import CoreMedia
import Foundation
import Speech
import XCTest
@testable import AppleSpeechSupport
@testable import AppleTranscribe
@testable import RecordPrompts

/// `apple-transcribe` と `record-prompts` の引数解析・JSONL入出力・WAV生成を検証する単体テスト。
final class AppleSpeechTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("apple-speech-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let tempDir {
            try? FileManager.default.removeItem(at: tempDir)
        }
    }

    func testAppleTranscribeOptionsDefaultsAndFlags() throws {
        let defaults = try AppleTranscribeOptions.parse(arguments: [
            "--manifest", "data/test/manifest.jsonl",
            "--out", "runs/exp01/out.jsonl",
        ])
        XCTAssertEqual(defaults.manifestPath, "data/test/manifest.jsonl")
        XCTAssertEqual(defaults.outPath, "runs/exp01/out.jsonl")
        XCTAssertEqual(defaults.transcriber, .dictation)
        XCTAssertEqual(defaults.locale, "ja-JP")
        XCTAssertFalse(defaults.useGlossary)
        XCTAssertFalse(defaults.showHelp)

        let custom = try AppleTranscribeOptions.parse(arguments: [
            "--manifest=in.jsonl",
            "--out=out.jsonl",
            "--transcriber=speech",
            "--locale=en-US",
            "--use-glossary",
        ])
        XCTAssertEqual(custom.manifestPath, "in.jsonl")
        XCTAssertEqual(custom.outPath, "out.jsonl")
        XCTAssertEqual(custom.transcriber, .speech)
        XCTAssertEqual(custom.locale, "en-US")
        XCTAssertTrue(custom.useGlossary)

        let help = try AppleTranscribeOptions.parse(arguments: ["--help"])
        XCTAssertTrue(help.showHelp)
    }

    func testAppleTranscribeOptionsRejectsInvalidArgs() {
        XCTAssertThrowsError(try AppleTranscribeOptions.parse(arguments: ["--out", "a.jsonl"]))
        XCTAssertThrowsError(try AppleTranscribeOptions.parse(arguments: ["--manifest", "a.jsonl"]))
        XCTAssertThrowsError(try AppleTranscribeOptions.parse(arguments: [
            "--manifest", "a.jsonl", "--out", "b.jsonl", "--transcriber", "whisper",
        ]))
        XCTAssertThrowsError(try AppleTranscribeOptions.parse(arguments: [
            "--manifest", "a.jsonl", "--out", "b.jsonl", "--unknown",
        ]))
    }

    func testTranscriptAccumulatorReplacesLaterOrSameStartSegments() {
        func t(_ seconds: Double) -> CMTime { CMTime(seconds: seconds, preferredTimescale: 16_000) }
        var acc = TranscriptAccumulator()
        acc.add(start: t(0), text: "きっと")
        acc.add(start: t(0), text: "GitHubに")
        acc.add(start: t(1.5), text: "プッシュ")
        acc.add(start: t(1.5), text: "プッシュしました ")
        XCTAssertEqual(acc.text, "GitHubにプッシュしました")

        acc.add(start: t(1.0), text: "push")
        XCTAssertEqual(acc.text, "GitHubにpush")
        XCTAssertEqual(TranscriptAccumulator().text, "")
    }

    func testSystemNameFormatting() {
        XCTAssertEqual(TranscriberKind.dictation.systemName(useGlossary: false), "apple-dictation")
        XCTAssertEqual(TranscriberKind.dictation.systemName(useGlossary: true), "apple-dictation-glossary")
        XCTAssertEqual(TranscriberKind.speech.systemName(useGlossary: false), "apple-speech")
        XCTAssertEqual(TranscriberKind.speech.systemName(useGlossary: true), "apple-speech-glossary")
    }

    func testRecordPromptsOptionsParsing() throws {
        let parsed = try RecordPromptsOptions.parse(arguments: [
            "--manifest", "prompts.jsonl",
            "--out-dir", "data/test-user",
        ])
        XCTAssertEqual(parsed.manifestPath, "prompts.jsonl")
        XCTAssertEqual(parsed.outDirPath, "data/test-user")
        XCTAssertFalse(parsed.showHelp)

        let help = try RecordPromptsOptions.parse(arguments: ["-h"])
        XCTAssertTrue(help.showHelp)

        XCTAssertThrowsError(try RecordPromptsOptions.parse(arguments: ["--manifest", "prompts.jsonl"]))
    }

    func testTranscribeManifestAndGlossaryExtraction() throws {
        let audioDir = tempDir.appendingPathComponent("audio", isDirectory: true)
        try FileManager.default.createDirectory(at: audioDir, withIntermediateDirectories: true)
        let wavURL = audioDir.appendingPathComponent("u-001.wav")
        try WavWriter.write(samples: [0, 100, -100], to: wavURL)

        let manifestURL = tempDir.appendingPathComponent("manifest.jsonl")
        let jsonl = """
        {"id":"u-001","split":"test-synth","audio_path":"audio/u-001.wav","spoken_text":"パイトーチ","glossary":[{"surface":"PyTorch","reading":"パイトーチ"},{"surface":"Dataset","reading":"データセット"},{"surface":"PyTorch","reading":"パイトーチ"},{"surface":"  "}]}
        """
        try jsonl.write(to: manifestURL, atomically: true, encoding: .utf8)

        let entries = try ManifestIO.loadTranscribeManifest(from: manifestURL)
        XCTAssertEqual(entries.count, 1)
        XCTAssertEqual(entries[0].id, "u-001")
        XCTAssertEqual(entries[0].audioPath, "audio/u-001.wav")
        XCTAssertEqual(entries[0].glossarySurfaces(), ["PyTorch", "Dataset"])

        let resolved = try ManifestIO.resolveAudioURL(audioPath: entries[0].audioPath, manifestURL: manifestURL)
        XCTAssertEqual(resolved.path, wavURL.standardizedFileURL.path)
    }

    func testTranscriptionResultRowJSONLEncoding() throws {
        let row = TranscriptionResultRow(
            id: "u-001",
            system: "apple-dictation-glossary",
            stage: "asr",
            hyp: "PyTorchのDataLoaderで読み込みます",
            latencySeconds: 0.42
        )
        let lineData = try ManifestIO.encodeJSONLine(row)
        XCTAssertEqual(lineData.last, 0x0A)

        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: lineData) as? [String: Any])
        XCTAssertEqual(obj["id"] as? String, "u-001")
        XCTAssertEqual(obj["system"] as? String, "apple-dictation-glossary")
        XCTAssertEqual(obj["stage"] as? String, "asr")
        XCTAssertEqual(obj["hyp"] as? String, "PyTorchのDataLoaderで読み込みます")
        XCTAssertEqual(try XCTUnwrap(obj["latency_s"] as? Double), 0.42, accuracy: 1e-9)
    }

    func testPromptManifestPreservesFieldsAndTracksResumeIDs() throws {
        let promptsURL = tempDir.appendingPathComponent("prompts.jsonl")
        let promptsText = """
        {"id":"rec-001","spoken_text":"パイトーチのデータローダーで読み込みます","target_text":"PyTorchのDataLoaderで読み込みます。","terms":["PyTorch","DataLoader"],"fillers":0}
        {"id":"rec-002","spoken_text":"エヌシーシーエルで分散学習します","domain":"ml-research"}
        """
        try promptsText.write(to: promptsURL, atomically: true, encoding: .utf8)

        let prompts = try ManifestIO.loadPromptManifest(from: promptsURL)
        XCTAssertEqual(prompts.count, 2)
        XCTAssertEqual(prompts[0].id, "rec-001")
        XCTAssertEqual(prompts[0].spokenText, "パイトーチのデータローダーで読み込みます")

        let outManifestURL = tempDir.appendingPathComponent("out/manifest.jsonl")
        XCTAssertEqual(try ManifestIO.loadRecordedIDs(from: outManifestURL), [])

        let line = try ManifestIO.buildRecordedManifestLine(prompt: prompts[0], relativeAudioPath: "audio/rec-001.wav")
        try ManifestIO.appendLine(line, to: outManifestURL)

        let recordedIDs = try ManifestIO.loadRecordedIDs(from: outManifestURL)
        XCTAssertEqual(recordedIDs, ["rec-001"])

        let savedText = try String(contentsOf: outManifestURL, encoding: .utf8)
        let savedObj = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(savedText.utf8)) as? [String: Any])
        XCTAssertEqual(savedObj["id"] as? String, "rec-001")
        XCTAssertEqual(savedObj["audio_path"] as? String, "audio/rec-001.wav")
        XCTAssertEqual(savedObj["speaker"] as? String, "user")
        XCTAssertEqual(savedObj["source"] as? String, "user")
        XCTAssertEqual(savedObj["split"] as? String, "test-user")
        XCTAssertEqual(savedObj["target_text"] as? String, "PyTorchのDataLoaderで読み込みます。")
        XCTAssertEqual(savedObj["terms"] as? [String], ["PyTorch", "DataLoader"])
        XCTAssertEqual(savedObj["fillers"] as? Int, 0)
    }

    func testPromptManifestRejectsUnsafeOrDuplicateIDs() throws {
        let traversalURL = tempDir.appendingPathComponent("bad-id.jsonl")
        try "{\"id\":\"../escape\",\"spoken_text\":\"テスト\"}\n".write(to: traversalURL, atomically: true, encoding: .utf8)
        XCTAssertThrowsError(try ManifestIO.loadPromptManifest(from: traversalURL))

        let duplicateURL = tempDir.appendingPathComponent("dup-id.jsonl")
        let dupText = """
        {"id":"dup-1","spoken_text":"一つ目"}
        {"id":"dup-1","spoken_text":"二つ目"}
        """
        try dupText.write(to: duplicateURL, atomically: true, encoding: .utf8)
        XCTAssertThrowsError(try ManifestIO.loadPromptManifest(from: duplicateURL))
    }

    func testWavWriterProducesCanonical16kHzMono16BitPCM() throws {
        let samples: [Int16] = Array(repeating: 0, count: 16_000)
        var nonSilent = samples
        nonSilent[0] = 16_384
        nonSilent[1] = -16_384

        let wavData = try WavWriter.makeWavData(samples: nonSilent)
        XCTAssertEqual(wavData.count, 44 + 16_000 * 2)
        XCTAssertEqual(String(data: wavData.subdata(in: 0..<4), encoding: .ascii), "RIFF")
        XCTAssertEqual(String(data: wavData.subdata(in: 8..<12), encoding: .ascii), "WAVE")
        XCTAssertEqual(String(data: wavData.subdata(in: 12..<16), encoding: .ascii), "fmt ")
        XCTAssertEqual(String(data: wavData.subdata(in: 36..<40), encoding: .ascii), "data")

        let wavURL = tempDir.appendingPathComponent("test.wav")
        try WavWriter.write(samples: nonSilent, to: wavURL)

        let audioFile = try AVAudioFile(forReading: wavURL)
        XCTAssertEqual(audioFile.fileFormat.sampleRate, 16_000.0)
        XCTAssertEqual(audioFile.fileFormat.channelCount, 1)
        XCTAssertEqual(audioFile.length, 16_000)

        let stats = WavWriter.computeStats(samples: nonSilent)
        XCTAssertEqual(stats.durationSeconds, 1.0, accuracy: 1e-9)
        XCTAssertEqual(stats.peakDBFS, -6.0206, accuracy: 0.01)

        let silentStats = WavWriter.computeStats(samples: [0, 0, 0])
        XCTAssertTrue(silentStats.peakDBFS.isInfinite && silentStats.peakDBFS < 0)
    }

    func testAudioLoaderDirectReadInt16() throws {
        let samples16k: [Int16] = (0..<40_000).map { i in
            Int16(8000.0 * sin(2.0 * Double.pi * 440.0 * Double(i) / 16_000.0))
        }
        let wav16kURL = tempDir.appendingPathComponent("tone16k.wav")
        try WavWriter.write(samples: samples16k, to: wav16kURL)

        let int16Target = try XCTUnwrap(
            AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true)
        )
        let int16Inputs = try AudioLoader.loadAnalyzerInputs(from: wav16kURL, targetFormat: int16Target)
        XCTAssertEqual(int16Inputs.count, 3)
        XCTAssertEqual(totalDurationSeconds(int16Inputs), 2.5, accuracy: 0.01)
    }

    func testAudioLoaderDirectReadInt16NonInterleaved() throws {
        let samples16k: [Int16] = (0..<40_000).map { i in
            Int16(8000.0 * sin(2.0 * Double.pi * 440.0 * Double(i) / 16_000.0))
        }
        let wav16kURL = tempDir.appendingPathComponent("tone16k-ni.wav")
        try WavWriter.write(samples: samples16k, to: wav16kURL)

        let int16NonInterleaved = try XCTUnwrap(
            AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: false)
        )
        let inputs = try AudioLoader.loadAnalyzerInputs(from: wav16kURL, targetFormat: int16NonInterleaved)
        XCTAssertEqual(inputs.count, 3)
        XCTAssertEqual(totalDurationSeconds(inputs), 2.5, accuracy: 0.01)
    }

    func testAudioLoaderResampleAndDownmix48kStereo() throws {
        let stereoFormat = try XCTUnwrap(
            AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48_000, channels: 2, interleaved: false)
        )
        let wav48kURL = tempDir.appendingPathComponent("tone48k-stereo.wav")
        let fileSettings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 48_000.0,
            AVNumberOfChannelsKey: 2,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false,
        ]
        do {
            let stereoFile = try AVAudioFile(forWriting: wav48kURL, settings: fileSettings)
            let stereoBuffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: stereoFormat, frameCapacity: 48_000))
            stereoBuffer.frameLength = 48_000
            if let channels = stereoBuffer.floatChannelData {
                for i in 0..<48_000 {
                    let v = Float(0.25 * sin(2.0 * Double.pi * 440.0 * Double(i) / 48_000.0))
                    channels[0][i] = v
                    channels[1][i] = v
                }
            }
            try stereoFile.write(from: stereoBuffer)
        }

        let int16Target = try XCTUnwrap(
            AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true)
        )
        let convertedInputs = try AudioLoader.loadAnalyzerInputs(from: wav48kURL, targetFormat: int16Target)
        XCTAssertFalse(convertedInputs.isEmpty)
        XCTAssertEqual(totalDurationSeconds(convertedInputs), 1.0, accuracy: 0.05)
    }

    func testAudioLoaderEmptyWavReturnsEmptyArray() throws {
        let int16Target = try XCTUnwrap(
            AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true)
        )
        let emptyWavURL = tempDir.appendingPathComponent("empty.wav")
        try WavWriter.write(samples: [], to: emptyWavURL)
        let emptyInputs = try AudioLoader.loadAnalyzerInputs(from: emptyWavURL, targetFormat: int16Target)
        XCTAssertTrue(emptyInputs.isEmpty)
    }

    /// `AnalyzerInput` 配列の合計再生時間（秒）を求めるテスト補助関数。
    private func totalDurationSeconds(_ inputs: [AnalyzerInput]) -> Double {
        if #available(macOS 27, *) {
            return inputs.reduce(0.0) { $0 + $1.bufferDuration.seconds }
        }
        return inputs.reduce(0.0) { partial, item in
            let buf = item.buffer
            return partial + Double(buf.frameLength) / buf.format.sampleRate
        }
    }
}
