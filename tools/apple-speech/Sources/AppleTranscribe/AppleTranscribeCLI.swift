import AppleSpeechSupport
import Darwin
import Foundation

/// `apple-transcribe` コマンドの解析済みCLIオプション。
public struct AppleTranscribeOptions: Sendable, Equatable {
    public let manifestPath: String
    public let outPath: String
    public let transcriber: TranscriberKind
    public let locale: String
    public let useGlossary: Bool
    public let showHelp: Bool

    /// コマンドの使い方メッセージを返す。
    public static let helpText = """
    使い方: apple-transcribe --manifest <path> --out <path> [オプション]

    manifest JSONL に記載された音声ファイルを macOS 標準の SpeechAnalyzer で認識し、
    推論結果を JSONL（id, system, stage, hyp, latency_s）で出力します。

    必須オプション:
      --manifest <path>              入力 manifest JSONL のパス
      --out <path>                   出力 JSONL のパス（親ディレクトリは自動作成）

    任意オプション:
      --transcriber <dictation|speech>  使用するモジュール（既定: dictation）
      --locale <id>                  認識ロケール（既定: ja-JP）
      --use-glossary                 各行の glossary.surface を AnalysisContext.contextualStrings へ渡す
                                     （DictationTranscriber のみ有効とされ、speech 指定時は警告を出します）
      -h, --help                     このヘルプを表示して終了
    """

    /// コマンドライン引数（先頭の実行ファイル名を除く）を解析する。
    public static func parse(arguments: [String]) throws -> AppleTranscribeOptions {
        var parser = CLIArgumentParser(arguments: arguments)
        var manifestPath: String?
        var outPath: String?
        var transcriber: TranscriberKind = .dictation
        var locale = "ja-JP"
        var useGlossary = false

        while let arg = parser.nextToken() {
            let (name, inlineValue) = CLIArgumentParser.splitOption(arg)
            switch name {
            case "-h", "--help":
                return AppleTranscribeOptions(
                    manifestPath: "",
                    outPath: "",
                    transcriber: .dictation,
                    locale: "ja-JP",
                    useGlossary: false,
                    showHelp: true
                )
            case "--manifest":
                manifestPath = try parser.nextValue(for: "--manifest", inlineValue: inlineValue)
            case "--out":
                outPath = try parser.nextValue(for: "--out", inlineValue: inlineValue)
            case "--transcriber":
                let raw = try parser.nextValue(for: "--transcriber", inlineValue: inlineValue)
                guard let parsed = TranscriberKind(rawValue: raw) else {
                    throw CLIError.invalidUsage("--transcriber には dictation または speech を指定してください（指定値: \(raw)）。")
                }
                transcriber = parsed
            case "--locale":
                locale = try parser.nextValue(for: "--locale", inlineValue: inlineValue)
            case "--use-glossary":
                guard inlineValue == nil else {
                    throw CLIError.invalidUsage("--use-glossary は値を取らないフラグです。")
                }
                useGlossary = true
            default:
                throw CLIError.invalidUsage("不明なオプションです: \(arg)")
            }
        }

        guard let manifestPath else {
            throw CLIError.invalidUsage("--manifest は必須です。")
        }
        guard let outPath else {
            throw CLIError.invalidUsage("--out は必須です。")
        }

        return AppleTranscribeOptions(
            manifestPath: manifestPath,
            outPath: outPath,
            transcriber: transcriber,
            locale: locale,
            useGlossary: useGlossary,
            showHelp: false
        )
    }
}

/// `apple-transcribe` 実行ファイルのエントリポイント。
@main
struct AppleTranscribeMain {
    static func main() async {
        do {
            let options = try AppleTranscribeOptions.parse(arguments: Array(CommandLine.arguments.dropFirst()))
            if options.showHelp {
                print(AppleTranscribeOptions.helpText)
                return
            }
            try await run(options: options)
        } catch let error as CLIError {
            logStderr("エラー: \(error.localizedDescription)")
            // 長いヘルプでエラー行が画面外へ流れないよう、引数の誤りでは案内の1行だけを出す。
            if case .invalidUsage = error {
                logStderr("使い方は apple-transcribe --help で表示できます。")
            }
            Darwin.exit(error.exitCode)
        } catch {
            logStderr("エラー: \(error.localizedDescription)")
            Darwin.exit(1)
        }
    }

    /// 資産確認・ウォームアップ・全発話の推論とJSONL書き出しを順に実行する。
    private static func run(options: AppleTranscribeOptions) async throws {
        if options.useGlossary && options.transcriber == .speech {
            logStderr("警告: --use-glossary は DictationTranscriber でのみ有効とされています。SpeechTranscriber では contextualStrings が反映されない場合があります。")
        }

        let manifestURL = URL(fileURLWithPath: options.manifestPath).standardizedFileURL
        let outURL = URL(fileURLWithPath: options.outPath).standardizedFileURL

        let entries = try ManifestIO.loadTranscribeManifest(from: manifestURL)
        logStderr("[info] manifest読み込み完了: \(entries.count)件 (\(manifestURL.path))")

        let runner = try await SpeechRunner.prepare(
            kind: options.transcriber,
            localeIdentifier: options.locale,
            useGlossary: options.useGlossary
        )

        do {
            let fm = FileManager.default
            try fm.createDirectory(at: outURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            fm.createFile(atPath: outURL.path, contents: nil)

            if let firstEntry = entries.first {
                let firstAudioURL = try ManifestIO.resolveAudioURL(audioPath: firstEntry.audioPath, manifestURL: manifestURL)
                let warmUpInputs = try AudioLoader.loadAnalyzerInputs(from: firstAudioURL, targetFormat: runner.analyzerFormat)
                try await runner.warmUp(inputs: warmUpInputs, glossarySurfaces: firstEntry.glossarySurfaces())
            }

            let systemName = options.transcriber.systemName(useGlossary: options.useGlossary)

            for (idx, entry) in entries.enumerated() {
                let audioURL = try ManifestIO.resolveAudioURL(audioPath: entry.audioPath, manifestURL: manifestURL)
                let inputs = try AudioLoader.loadAnalyzerInputs(from: audioURL, targetFormat: runner.analyzerFormat)
                let surfaces = entry.glossarySurfaces()

                let (hyp, latencySeconds) = try await runner.transcribe(inputs: inputs, glossarySurfaces: surfaces)
                let row = TranscriptionResultRow(
                    id: entry.id,
                    system: systemName,
                    stage: "asr",
                    hyp: hyp,
                    latencySeconds: latencySeconds
                )
                let lineData = try ManifestIO.encodeJSONLine(row)
                try ManifestIO.appendLine(lineData, to: outURL)

                logStderr(String(format: "[%d/%d] %@ (%.3fs): %@", idx + 1, entries.count, entry.id, latencySeconds, hyp))
            }

            await runner.endRetention()
            logStderr("[done] \(entries.count)件の結果を \(outURL.path) へ出力しました。")
        } catch {
            await runner.endRetention()
            throw error
        }
    }
}
