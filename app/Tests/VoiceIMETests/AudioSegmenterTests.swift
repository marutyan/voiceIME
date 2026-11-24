import Foundation
import XCTest
@testable import VoiceIMECore

/// 音量列による区間区切り判定（300ms背景雑音測定・600ms無音・20秒上限）とWAV生成を検証するテスト。
final class AudioSegmenterTests: XCTestCase {
    func testPureSilenceProducesNoSegments() {
        var segmenter = AudioSegmenter()
        // 3秒間（150フレーム × 20ms）の完全無音
        let closed = segmenter.pushFrameLevels([Float](repeating: 0.0, count: 150))
        XCTAssertTrue(closed.isEmpty)
        XCTAssertNil(segmenter.finish())
    }

    func testInitial300msCalibrationLearnsBackgroundNoiseAndIgnoresSteadyNoise() {
        var segmenter = AudioSegmenter()
        // 冒頭300ms（15フレーム）の定常雑音（RMS 0.010）。既定の最小しきい値0.006より大きいが、
        // 300msで学習した後はしきい値が 0.010 * 3 = 0.030 になるため区間を開かない。
        let steadyNoise = [Float](repeating: 0.010, count: 150) // 3.0秒
        XCTAssertTrue(segmenter.pushFrameLevels(steadyNoise).isEmpty)
        XCTAssertNil(segmenter.finish())
        XCTAssertEqual(segmenter.noiseFloor, 0.010, accuracy: 0.001)
        XCTAssertEqual(segmenter.threshold, 0.030, accuracy: 0.003)

        // 学習した雑音より大きい発話（RMS 0.080）は区間を開き、600ms無音（30フレーム）で閉じる。
        var speechThenSilence: [Float] = []
        speechThenSilence.append(contentsOf: repeatElement(0.080, count: 25)) // 500ms発話
        speechThenSilence.append(contentsOf: repeatElement(0.010, count: 30)) // 600ms背景雑音
        let closed = segmenter.pushFrameLevels(speechThenSilence)
        XCTAssertEqual(closed.count, 1)
        // フレーム150〜174が発話、末尾余白200ms（10フレーム）を残して終了フレームは185。
        XCTAssertEqual(closed[0].startFrame, 150)
        XCTAssertEqual(closed[0].endFrame, 185)
        XCTAssertEqual(closed[0].samples.count, 35 * 320)
    }

    func testSpeechStartingDuringFirst300msIsPreservedWithoutCorruptingNoiseFloor() {
        var segmenter = AudioSegmenter()
        // 冒頭0msから話し始めた場合（RMS 0.10 >= maxCalibrationNoiseRMS 0.02）
        let speech = [Float](repeating: 0.10, count: 40) // 800ms
        XCTAssertTrue(segmenter.pushFrameLevels(speech).isEmpty)
        XCTAssertLessThan(segmenter.noiseFloor, 0.005)

        let finalSegment = segmenter.finish()
        XCTAssertNotNil(finalSegment)
        XCTAssertEqual(finalSegment?.startFrame, 0)
        XCTAssertEqual(finalSegment?.endFrame, 40)
        XCTAssertEqual(finalSegment?.samples.count, 40 * 320)
    }

    func testShortSpeechEndingBefore300msCalibrationCompletesIsStillReturnedOnFinish() {
        var segmenter = AudioSegmenter()
        // 200ms（10フレーム）だけ話してすぐキーを離した場合
        let shortSpeech = [Float](repeating: 0.10, count: 10)
        XCTAssertTrue(segmenter.pushFrameLevels(shortSpeech).isEmpty)

        let finalSegment = segmenter.finish()
        XCTAssertNotNil(finalSegment)
        XCTAssertEqual(finalSegment?.startFrame, 0)
        XCTAssertEqual(finalSegment?.endFrame, 10)
        XCTAssertEqual(finalSegment?.samples.count, 10 * 320)
    }

    func testBriefClickNoiseDoesNotOpenSegment() {
        var segmenter = AudioSegmenter()
        var levels: [Float] = []
        levels.append(contentsOf: repeatElement(0.0, count: 20))  // 400ms無音
        levels.append(contentsOf: repeatElement(0.30, count: 2))  // 40ms（2フレーム）のクリック音
        levels.append(contentsOf: repeatElement(0.0, count: 40))  // 800ms無音

        XCTAssertTrue(segmenter.pushFrameLevels(levels).isEmpty)
        XCTAssertNil(segmenter.finish())
    }

    func testSilenceThresholdBoundary600msClosesWhile580msKeepsOpen() {
        var segmenter = AudioSegmenter()
        var levels: [Float] = []
        levels.append(contentsOf: repeatElement(0.0, count: 15))  // 0..14: 300ms校正
        levels.append(contentsOf: repeatElement(0.10, count: 20)) // 15..34: 400ms発話1
        levels.append(contentsOf: repeatElement(0.0, count: 29))  // 35..63: 580ms無音（600ms未満なので閉じない）
        levels.append(contentsOf: repeatElement(0.10, count: 20)) // 64..83: 400ms発話2（同一区間へ結合）
        levels.append(contentsOf: repeatElement(0.0, count: 30))  // 84..113: 600ms無音（ちょうど30フレームで閉じる）

        let closed = segmenter.pushFrameLevels(levels)
        XCTAssertEqual(closed.count, 1)
        // 15から始まり、最後の発話83の後ろに200ms（10フレーム）余白を残した94で閉じる。
        XCTAssertEqual(closed[0].startFrame, 15)
        XCTAssertEqual(closed[0].endFrame, 94)
        XCTAssertEqual(closed[0].samples.count, 79 * 320)
        XCTAssertNil(segmenter.finish())
    }

    func testTwoUtterancesSeparatedBy600msSilenceProduceTwoExactSegments() {
        var segmenter = AudioSegmenter()
        var levels: [Float] = []
        levels.append(contentsOf: repeatElement(0.0, count: 15))  // 0..14: 300ms校正
        levels.append(contentsOf: repeatElement(0.12, count: 25)) // 15..39: 500ms発話1
        levels.append(contentsOf: repeatElement(0.0, count: 35))  // 40..74: 700ms無音（フレーム69で閉じる）
        levels.append(contentsOf: repeatElement(0.12, count: 30)) // 75..104: 600ms発話2
        levels.append(contentsOf: repeatElement(0.0, count: 30))  // 105..134: 600ms無音（フレーム134で閉じる）

        let closed = segmenter.pushFrameLevels(levels)
        XCTAssertEqual(closed.count, 2)
        XCTAssertEqual(closed[0].startFrame, 15)
        XCTAssertEqual(closed[0].endFrame, 50) // 40 + 10フレーム余白
        XCTAssertEqual(closed[1].startFrame, 75)
        XCTAssertEqual(closed[1].endFrame, 115) // 105 + 10フレーム余白
        XCTAssertNil(segmenter.finish())
    }

    func testMaxInterval20SecondsCutsAtQuietestFrameInRecent5SecondWindow() {
        var segmenter = AudioSegmenter()
        // 0..14: 300ms無音校正
        // 15..1014: ちょうど1000フレーム（20.0秒）の連続発話
        // そのうち、区間内インデックス850..879（17.0秒〜17.6秒、全体フレーム865..894）を最も静かな0.015にする。
        var levels = [Float](repeating: 0.0, count: 15)
        var speech = [Float](repeating: 0.12, count: 1000)
        for i in 850 ..< 880 {
            speech[i] = 0.015
        }
        levels.append(contentsOf: speech)
        // さらに40フレーム（0.8秒）話し続けてfinishする
        levels.append(contentsOf: repeatElement(0.12, count: 40))

        let closed = segmenter.pushFrameLevels(levels)
        XCTAssertEqual(closed.count, 1)
        // 直近5秒（区間内750..999）で最も静かな0.015のうち最末尾は区間内インデックス879 → 880フレームで分割。
        // 全体フレームでは 15 ..< (15 + 880 = 895)。
        XCTAssertEqual(closed[0].startFrame, 15)
        XCTAssertEqual(closed[0].endFrame, 895)
        XCTAssertEqual(closed[0].samples.count, 880 * 320)

        let remainder = segmenter.finish()
        XCTAssertNotNil(remainder)
        // 残りは 895 ..< 1055（120 + 40 = 160フレーム）で欠落ゼロ。
        XCTAssertEqual(remainder?.startFrame, 895)
        XCTAssertEqual(remainder?.endFrame, 1055)
        XCTAssertEqual(remainder?.samples.count, 160 * 320)
    }

    func testPcmSamplesPreserveTrailingRemainderOnFinish() {
        var segmenter = AudioSegmenter()
        // 16000サンプル（1秒）＋端数37サンプルの一定振幅音声
        let samples = [Int16](repeating: 6000, count: 16_037)
        XCTAssertTrue(segmenter.push(samples: samples).isEmpty)
        let segment = segmenter.finish()
        XCTAssertEqual(segment?.samples.count, 16_037)
        XCTAssertEqual(segment?.samples, samples)
    }

    func testWavWriterCreatesValid16kHzMono16BitPcmHeader() throws {
        let samples: [Int16] = [0, 1000, -1000, 32767, -32768]
        let wav = try WavWriter.makeWavData(samples: samples)

        // 44バイトヘッダ + 5サンプル * 2バイト = 54バイト
        XCTAssertEqual(wav.count, 54)
        XCTAssertEqual(String(data: wav[0 ..< 4], encoding: .ascii), "RIFF")
        XCTAssertEqual(readUInt32LE(wav, offset: 4), 46) // 36 + 10
        XCTAssertEqual(String(data: wav[8 ..< 12], encoding: .ascii), "WAVE")
        XCTAssertEqual(String(data: wav[12 ..< 16], encoding: .ascii), "fmt ")
        XCTAssertEqual(readUInt32LE(wav, offset: 16), 16)
        XCTAssertEqual(readUInt16LE(wav, offset: 20), 1)     // PCM
        XCTAssertEqual(readUInt16LE(wav, offset: 22), 1)     // Mono
        XCTAssertEqual(readUInt32LE(wav, offset: 24), 16000) // 16kHz
        XCTAssertEqual(readUInt32LE(wav, offset: 28), 32000) // ByteRate = 16000 * 2
        XCTAssertEqual(readUInt16LE(wav, offset: 32), 2)     // BlockAlign
        XCTAssertEqual(readUInt16LE(wav, offset: 34), 16)    // BitsPerSample
        XCTAssertEqual(String(data: wav[36 ..< 40], encoding: .ascii), "data")
        XCTAssertEqual(readUInt32LE(wav, offset: 40), 10)    // 5 * 2
    }

    private func readUInt16LE(_ data: Data, offset: Int) -> UInt16 {
        UInt16(data[offset]) | (UInt16(data[offset + 1]) << 8)
    }

    private func readUInt32LE(_ data: Data, offset: Int) -> UInt32 {
        UInt32(data[offset])
            | (UInt32(data[offset + 1]) << 8)
            | (UInt32(data[offset + 2]) << 16)
            | (UInt32(data[offset + 3]) << 24)
    }
}
