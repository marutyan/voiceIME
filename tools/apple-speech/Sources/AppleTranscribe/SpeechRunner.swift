import AVFoundation
import AppleSpeechSupport
import CoreMedia
import Foundation
import Speech

/// 使用するSpeechフレームワークの文字起こしモジュール種別。
public enum TranscriberKind: String, Sendable, Equatable {
    case dictation
    case speech

    /// 出力JSONLの `system` 列へ記録する識別子を返す。
    public func systemName(useGlossary: Bool) -> String {
        let base = "apple-\(rawValue)"
        return useGlossary ? "\(base)-glossary" : base
    }
}

/// メモリ上に読み込み済みの `AnalyzerInput` 配列を `SpeechAnalyzer` へ渡すための非同期シーケンス。
struct AnalyzerInputArraySequence: AsyncSequence, Sendable {
    typealias Element = AnalyzerInput

    let inputs: [AnalyzerInput]

    struct Iterator: AsyncIteratorProtocol {
        let inputs: [AnalyzerInput]
        var index: Int = 0

        mutating func next() async -> AnalyzerInput? {
            guard index < inputs.count else { return nil }
            defer { index += 1 }
            return inputs[index]
        }
    }

    func makeAsyncIterator() -> Iterator {
        Iterator(inputs: inputs)
    }
}

/// 文字起こし結果を音声区間ごとにまとめ、1発話分の文字列を作る。
/// 同じ区間またはそれより後ろから始まる結果が届いた場合は、先に届いた結果を新しい結果で置き換える。
struct TranscriptAccumulator: Sendable {
    private var segments: [(start: CMTime, text: String)] = []

    /// 開始時刻 `start` の結果を追加し、それ以降に始まる既存の結果を取り除く。
    mutating func add(start: CMTime, text: String) {
        segments.removeAll { CMTimeCompare($0.start, start) >= 0 }
        segments.append((start, text))
    }

    /// 開始時刻順に連結し、前後の空白を除いた文字列。
    var text: String {
        segments.map(\.text).joined().trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

/// 言語資産の準備、初回実行によるウォームアップ、発話単位の認識と遅延計測を担う実行器。
struct SpeechRunner: Sendable {
    let kind: TranscriberKind
    let resolvedLocale: Locale
    let analyzerFormat: AVAudioFormat
    let useGlossary: Bool

    /// 16kHzモノラル16bit WAVを基準に互換フォーマットの探索ヒントを作る。
    private static func makeNaturalHintFormat() -> AVAudioFormat {
        AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: 16_000,
            channels: 1,
            interleaved: true
        )!
    }

    /// ロケール解決、AssetInventoryによる言語資産の確認と必要時のダウンロード、互換音声形式の取得を行う。
    static func prepare(kind: TranscriberKind, localeIdentifier: String, useGlossary: Bool) async throws -> SpeechRunner {
        let requestedLocale = Locale(identifier: localeIdentifier)
        let resolvedLocale: Locale
        let probeModule: any SpeechModule

        switch kind {
        case .dictation:
            guard let supported = await DictationTranscriber.supportedLocale(equivalentTo: requestedLocale) else {
                let locales = await DictationTranscriber.supportedLocales.map(\.identifier).sorted()
                if locales.isEmpty {
                    throw CLIError.runtime(
                        "DictationTranscriber の対応ロケールを取得できませんでした（空の一覧）。"
                            + "サンドボックス制限や音声認識サービスへの接続不可が原因の可能性があります。"
                    )
                }
                throw CLIError.runtime(
                    "DictationTranscriber はロケール '\(localeIdentifier)' に対応していません。対応一覧: \(locales.joined(separator: ", "))"
                )
            }
            resolvedLocale = supported
            probeModule = DictationTranscriber(locale: resolvedLocale, preset: .shortDictation)

        case .speech:
            guard SpeechTranscriber.isAvailable else {
                throw CLIError.runtime(
                    "この環境では SpeechTranscriber を利用できません（非対応環境、またはサンドボックス等により音声認識サービスへ接続できない可能性があります）。"
                )
            }
            guard let supported = await SpeechTranscriber.supportedLocale(equivalentTo: requestedLocale) else {
                let locales = await SpeechTranscriber.supportedLocales.map(\.identifier).sorted()
                if locales.isEmpty {
                    throw CLIError.runtime(
                        "SpeechTranscriber の対応ロケールを取得できませんでした（空の一覧）。"
                            + "サンドボックス制限や音声認識サービスへの接続不可が原因の可能性があります。"
                    )
                }
                throw CLIError.runtime(
                    "SpeechTranscriber はロケール '\(localeIdentifier)' に対応していません。対応一覧: \(locales.joined(separator: ", "))"
                )
            }
            resolvedLocale = supported
            probeModule = SpeechTranscriber(locale: resolvedLocale, preset: .transcription)
        }

        logStderr("[asset] モジュール: \(kind.rawValue), ロケール: \(localeIdentifier) -> \(resolvedLocale.identifier)")
        try await ensureAssetsInstalled(for: probeModule, locale: resolvedLocale)

        let naturalFormat = makeNaturalHintFormat()
        guard let bestFormat = await SpeechAnalyzer.bestAvailableAudioFormat(
            compatibleWith: [probeModule],
            considering: naturalFormat
        ) else {
            throw CLIError.runtime("SpeechAnalyzer で利用可能な音声フォーマットを取得できませんでした。")
        }

        logStderr(
            "[asset] 解析用音声フォーマット: \(Int(bestFormat.sampleRate))Hz, \(bestFormat.channelCount)ch, \(bestFormat.commonFormat.description)"
        )

        return SpeechRunner(
            kind: kind,
            resolvedLocale: resolvedLocale,
            analyzerFormat: bestFormat,
            useGlossary: useGlossary
        )
    }

    /// 言語資産の状態を確認し、未導入であればダウンロードとインストールを実行する。状態はstderrへ出す。
    private static func ensureAssetsInstalled(for module: any SpeechModule, locale: Locale) async throws {
        let status = await AssetInventory.status(forModules: [module])
        logStderr("[asset] 言語資産の状態 (\(locale.identifier)): \(assetStatusLabel(status))")

        if status == .unsupported {
            throw CLIError.runtime("ロケール '\(locale.identifier)' の言語資産はこの環境でサポートされていません。")
        }

        // CLI実行時に既インストール済み資産でも `assetLocaleNotAllocated` を避けるため、未予約なら予約する。
        let reservedLocales = await AssetInventory.reservedLocales
        let targetBCP47 = locale.identifier(.bcp47)
        if !reservedLocales.contains(where: { $0.identifier(.bcp47) == targetBCP47 }) {
            do {
                let reserved = try await AssetInventory.reserve(locale: locale)
                logStderr("[asset] ロケール \(locale.identifier) の予約を実行しました (成功: \(reserved))")
            } catch {
                let reservedList = reservedLocales.map(\.identifier).joined(separator: ", ")
                throw CLIError.runtime(
                    "ロケール '\(locale.identifier)' の予約に失敗しました (\(error.localizedDescription))。"
                        + "予約済みロケール (\(reservedLocales.count)/\(AssetInventory.maximumReservedLocales)): \(reservedList)"
                )
            }
        }

        let installationRequest: AssetInstallationRequest?
        do {
            installationRequest = try await AssetInventory.assetInstallationRequest(supporting: [module])
        } catch {
            let reserved = await AssetInventory.reservedLocales.map(\.identifier)
            throw CLIError.runtime(
                "言語資産のインストール準備に失敗しました (\(error.localizedDescription))。"
                    + "予約済みロケール (\(reserved.count)/\(AssetInventory.maximumReservedLocales)): \(reserved.joined(separator: ", "))"
            )
        }

        if let installationRequest {
            logStderr("[asset] 言語資産をダウンロード・インストールします...")
            let progress = installationRequest.progress
            let progressTask = Task {
                var lastPercent = -1
                while !Task.isCancelled {
                    let percent = Int((progress.fractionCompleted * 100.0).rounded())
                    if percent != lastPercent {
                        logStderr("[asset] ダウンロード進捗: \(percent)%")
                        lastPercent = percent
                    }
                    try? await Task.sleep(for: .seconds(1))
                }
            }
            defer { progressTask.cancel() }

            do {
                try await installationRequest.downloadAndInstall()
            } catch {
                throw CLIError.runtime("言語資産のダウンロードに失敗しました: \(error.localizedDescription)")
            }
            logStderr("[asset] 言語資産のインストールが完了しました。")
        } else {
            logStderr("[asset] 言語資産はインストール済みのためダウンロードを省略します。")
        }
    }

    /// モデルをメモリ上へ載せて初回コンパイル等を済ませるためのウォームアップを1回だけ実行する。
    func warmUp(inputs: [AnalyzerInput], glossarySurfaces: [String]) async throws {
        guard !inputs.isEmpty else { return }
        logStderr("[warmup] 初回実行によるモデル準備を開始します...")
        let (_, elapsed) = try await runSingleTranscription(inputs: inputs, glossarySurfaces: glossarySurfaces)
        logStderr(String(format: "[warmup] モデル準備が完了しました (%.3f秒、計測対象外)", elapsed))
    }

    /// 読み込み済みの音声入力を認識し、認識文字列と推論時間（秒）を返す。
    func transcribe(inputs: [AnalyzerInput], glossarySurfaces: [String]) async throws -> (hyp: String, latencySeconds: Double) {
        guard !inputs.isEmpty else {
            return ("", 0.0)
        }
        return try await runSingleTranscription(inputs: inputs, glossarySurfaces: glossarySurfaces)
    }

    /// プロセス終了時にモデル保持を解放する。
    func endRetention() async {
        await SpeechModels.endRetention()
    }

    /// 1発話分のSpeechAnalyzerセッションを実行し、開始から最終結果確定までの経過秒数を測る。
    private func runSingleTranscription(
        inputs: [AnalyzerInput],
        glossarySurfaces: [String]
    ) async throws -> (hyp: String, latencySeconds: Double) {
        let clock = ContinuousClock()
        let start = clock.now

        let options = SpeechAnalyzer.Options(priority: .userInitiated, modelRetention: .processLifetime)

        let hyp: String
        switch kind {
        case .dictation:
            let transcriber = DictationTranscriber(locale: resolvedLocale, preset: .shortDictation)
            let analyzer = SpeechAnalyzer(modules: [transcriber], options: options)
            try await applyContextIfNeeded(to: analyzer, glossarySurfaces: glossarySurfaces)
            try await analyzer.prepareToAnalyze(in: analyzerFormat)

            // `.shortDictation` の結果は `resultsFinalizationTime` が0のまま届き `isFinal` が常にfalseになるため、
            // `isFinal` で絞らず、区間の開始時刻が同じか後ろの結果を後着のもので置き換えて確定文字列を作る。
            let resultTask = Task<String, Error> {
                var transcript = TranscriptAccumulator()
                for try await result in transcriber.results {
                    transcript.add(start: result.range.start, text: String(result.text.characters))
                }
                return transcript.text
            }
            hyp = try await feedAndCollect(analyzer: analyzer, inputs: inputs, resultTask: resultTask)

        case .speech:
            let transcriber = SpeechTranscriber(locale: resolvedLocale, preset: .transcription)
            let analyzer = SpeechAnalyzer(modules: [transcriber], options: options)
            try await applyContextIfNeeded(to: analyzer, glossarySurfaces: glossarySurfaces)
            try await analyzer.prepareToAnalyze(in: analyzerFormat)

            let resultTask = Task<String, Error> {
                var transcript = AttributedString()
                for try await result in transcriber.results {
                    if result.isFinal {
                        transcript += result.text
                    }
                }
                return String(transcript.characters).trimmingCharacters(in: .whitespacesAndNewlines)
            }
            hyp = try await feedAndCollect(analyzer: analyzer, inputs: inputs, resultTask: resultTask)
        }

        let duration = start.duration(to: clock.now)
        let seconds = Double(duration.components.seconds) + Double(duration.components.attoseconds) / 1e18
        return (hyp, seconds)
    }

    /// `--use-glossary` が有効かつ用語が存在する場合に `AnalysisContext.contextualStrings` を設定する。
    private func applyContextIfNeeded(to analyzer: SpeechAnalyzer, glossarySurfaces: [String]) async throws {
        guard useGlossary, !glossarySurfaces.isEmpty else { return }
        let context = AnalysisContext()
        context.contextualStrings[.general] = glossarySurfaces
        try await analyzer.setContext(context)
    }

    /// 音声入力シーケンスを流し込んで終了処理を行い、失敗時は結果タスクを確実にキャンセルする。
    private func feedAndCollect(
        analyzer: SpeechAnalyzer,
        inputs: [AnalyzerInput],
        resultTask: Task<String, Error>
    ) async throws -> String {
        do {
            let lastSampleTime = try await analyzer.analyzeSequence(AnalyzerInputArraySequence(inputs: inputs))
            if let lastSampleTime {
                try await analyzer.finalizeAndFinish(through: lastSampleTime)
            } else {
                try await analyzer.finalizeAndFinishThroughEndOfInput()
            }
            return try await resultTask.value
        } catch {
            await analyzer.cancelAndFinishNow()
            resultTask.cancel()
            throw error
        }
    }

    /// `AssetInventory.Status` をログ出力用の分かりやすい日本語表現へ変換する。
    private static func assetStatusLabel(_ status: AssetInventory.Status) -> String {
        switch status {
        case .unsupported:
            return "未対応 (unsupported)"
        case .downloading:
            return "ダウンロード中 (downloading)"
        case .supported:
            return "未インストール・取得可能 (supported)"
        case .installed:
            return "インストール済み (installed)"
        @unknown default:
            return "不明 (\(status))"
        }
    }
}

private extension AVAudioCommonFormat {
    var description: String {
        switch self {
        case .pcmFormatFloat32: return "Float32"
        case .pcmFormatFloat64: return "Float64"
        case .pcmFormatInt16: return "Int16"
        case .pcmFormatInt32: return "Int32"
        case .otherFormat: return "other"
        @unknown default: return "unknown"
        }
    }
}
