import AppleSpeechSupport
import Darwin
import Foundation

/// `record-prompts` コマンドの解析済みCLIオプション。
public struct RecordPromptsOptions: Sendable, Equatable {
    public let manifestPath: String
    public let outDirPath: String
    /// manifestの`split`へ書く値。開発用の録音（dev-user）と最終評価用（test-user）を分けるため。
    public var split: String = "test-user"
    public let showHelp: Bool

    /// コマンドの使い方メッセージを返す。
    public static let helpText = """
    使い方: record-prompts --manifest <prompts.jsonl> --out-dir <dir> [--split dev-user|test-user]

    prompts JSONL の各発話（id, spoken_text）を端末へ1件ずつ表示し、
    マイクから16kHzモノラル16bit WAVを録音して manifest.jsonl を追記生成します。

    必須オプション:
      --manifest <path>   入力 prompts JSONL のパス（各行に id と spoken_text を含む）
      --out-dir <dir>     出力先ディレクトリ（<dir>/audio/<id>.wav と <dir>/manifest.jsonl を保存）

    任意オプション:
      --split <名前>      manifestのsplitに書く値（既定 test-user）
      -h, --help          このヘルプを表示して終了

    対話操作:
      Enter               録音開始 / 録音停止 / 録音確定して次へ
      r + Enter           取り直し（録音中・停止後のどちらでも可）
      s + Enter           この発話を飛ばす
      q + Enter           途中終了（保存済みの録音と manifest.jsonl は残り、再実行時は録音済み id を飛ばします）
    """

    /// コマンドライン引数（先頭の実行ファイル名を除く）を解析する。
    public static func parse(arguments: [String]) throws -> RecordPromptsOptions {
        var parser = CLIArgumentParser(arguments: arguments)
        var manifestPath: String?
        var outDirPath: String?
        var split = "test-user"

        while let arg = parser.nextToken() {
            let (name, inlineValue) = CLIArgumentParser.splitOption(arg)
            switch name {
            case "-h", "--help":
                return RecordPromptsOptions(manifestPath: "", outDirPath: "", showHelp: true)
            case "--manifest":
                manifestPath = try parser.nextValue(for: "--manifest", inlineValue: inlineValue)
            case "--out-dir":
                outDirPath = try parser.nextValue(for: "--out-dir", inlineValue: inlineValue)
            case "--split":
                split = try parser.nextValue(for: "--split", inlineValue: inlineValue)
            default:
                throw CLIError.invalidUsage("不明なオプションです: \(arg)")
            }
        }

        guard let manifestPath else {
            throw CLIError.invalidUsage("--manifest は必須です。")
        }
        guard let outDirPath else {
            throw CLIError.invalidUsage("--out-dir は必須です。")
        }

        var options = RecordPromptsOptions(
            manifestPath: manifestPath,
            outDirPath: outDirPath,
            showHelp: false
        )
        options.split = split
        return options
    }
}

/// 1件のプロンプトに対する対話フローの確定結果。
enum PromptDecision {
    case saved
    case skipped
    case quit
}

/// `record-prompts` 実行ファイルのエントリポイント。
@main
struct RecordPromptsMain {
    static func main() async {
        do {
            let options = try RecordPromptsOptions.parse(arguments: Array(CommandLine.arguments.dropFirst()))
            if options.showHelp {
                print(RecordPromptsOptions.helpText)
                return
            }
            try await run(options: options)
        } catch let error as CLIError {
            logStderr("エラー: \(error.localizedDescription)")
            if case .invalidUsage = error {
                logStderr("\n\(RecordPromptsOptions.helpText)")
            }
            Darwin.exit(error.exitCode)
        } catch {
            logStderr("エラー: \(error.localizedDescription)")
            Darwin.exit(1)
        }
    }

    /// プロンプトの読み込み・録音済みIDのスキップ・マイク権限確認・対話録音ループを実行する。
    private static func run(options: RecordPromptsOptions) async throws {
        let promptsURL = URL(fileURLWithPath: options.manifestPath).standardizedFileURL
        let outDirURL = URL(fileURLWithPath: options.outDirPath).standardizedFileURL
        let audioDirURL = outDirURL.appendingPathComponent("audio", isDirectory: true)
        let outManifestURL = outDirURL.appendingPathComponent("manifest.jsonl")

        let allPrompts = try ManifestIO.loadPromptManifest(from: promptsURL)
        let recordedIDs = try ManifestIO.loadRecordedIDs(from: outManifestURL)
        let pending = allPrompts.filter { !recordedIDs.contains($0.id) }

        print("全 \(allPrompts.count) 件中、録音済み \(recordedIDs.count) 件をスキップします（残り \(pending.count) 件）。")
        guard !pending.isEmpty else {
            print("未録音の発話はありません。")
            return
        }

        try await MicrophoneRecorder.ensureMicrophonePermission()
        try FileManager.default.createDirectory(at: audioDirURL, withIntermediateDirectories: true)

        let recorder = MicrophoneRecorder()
        var savedCount = 0
        var skippedCount = 0

        for (index, prompt) in pending.enumerated() {
            let decision = try handleSinglePrompt(
                prompt: prompt,
                index: index + 1,
                total: pending.count,
                recorder: recorder,
                audioDirURL: audioDirURL,
                outManifestURL: outManifestURL,
                split: options.split
            )
            switch decision {
            case .saved:
                savedCount += 1
            case .skipped:
                skippedCount += 1
            case .quit:
                print("\n中断しました。今回保存: \(savedCount)件 / スキップ: \(skippedCount)件")
                print("保存済みのデータは \(outManifestURL.path) に残っています。再実行すると続きから再開します。")
                return
            }
        }

        print("\nすべて完了しました。今回保存: \(savedCount)件 / スキップ: \(skippedCount)件")
        print("出力manifest: \(outManifestURL.path)")
    }

    /// 1件のプロンプトについて、録音開始・停止・取り直し・スキップ・保存を対話的に処理する。
    private static func handleSinglePrompt(
        prompt: PromptRow,
        index: Int,
        total: Int,
        recorder: MicrophoneRecorder,
        audioDirURL: URL,
        outManifestURL: URL,
        split: String
    ) throws -> PromptDecision {
        while true {
            print("\n========================================")
            print("[\(index)/\(total)] id: \(prompt.id)")
            print("読み上げ文:")
            print("  \(prompt.spokenText)")
            print("========================================")

            let startChoice = promptInput("Enterで録音開始（sで飛ばす / qで終了）> ")
            guard let startChoice else {
                return .quit
            }
            switch startChoice {
            case "":
                break
            case "s", "S":
                print("スキップしました: \(prompt.id)")
                return .skipped
            case "q", "Q":
                return .quit
            default:
                print("Enter（録音開始）、s（飛ばす）、q（終了）のいずれかを入力してください。")
                continue
            }

            try recorder.start()
            let stopChoice = promptInput("● 録音中... もう一度Enterで停止（rで取り直し / sで飛ばす / qで終了）> ")

            guard let stopChoice else {
                recorder.cancel()
                return .quit
            }
            switch stopChoice {
            case "r", "R":
                recorder.cancel()
                print("取り直します。")
                continue
            case "s", "S":
                recorder.cancel()
                print("スキップしました: \(prompt.id)")
                return .skipped
            case "q", "Q":
                recorder.cancel()
                return .quit
            default:
                break
            }

            let samples = try recorder.stop()
            let stats = WavWriter.computeStats(samples: samples)
            let peakText = stats.peakDBFS.isFinite ? String(format: "%.1f dBFS", stats.peakDBFS) : "-inf dBFS"
            print(String(format: "録音停止: %.2f秒（最大音量 %@）", stats.durationSeconds, peakText))
            if samples.isEmpty || stats.peakDBFS < -50.0 {
                print("※ 音量が極端に小さいか無音です。マイク入力を確認のうえ、必要なら r で取り直してください。")
            }

            confirmLoop: while true {
                let confirm = promptInput("Enterで保存して次へ（rで取り直し / sで飛ばす / qで保存せず終了）> ")
                guard let confirm else {
                    return .quit
                }
                switch confirm {
                case "":
                    let relativePath = "audio/\(prompt.id).wav"
                    let wavURL = audioDirURL.appendingPathComponent("\(prompt.id).wav")
                    try WavWriter.write(samples: samples, to: wavURL)
                    let manifestLine = try ManifestIO.buildRecordedManifestLine(
                        prompt: prompt,
                        relativeAudioPath: relativePath,
                        split: split
                    )
                    try ManifestIO.appendLine(manifestLine, to: outManifestURL)
                    print("保存しました: \(wavURL.path)")
                    return .saved
                case "r", "R":
                    print("取り直します。")
                    break confirmLoop
                case "s", "S":
                    print("スキップしました: \(prompt.id)")
                    return .skipped
                case "q", "Q":
                    return .quit
                default:
                    print("Enter（保存）、r（取り直し）、s（飛ばす）、q（終了）のいずれかを入力してください。")
                }
            }
        }
    }

    /// プロンプトを表示して標準出力をフラッシュし、1行入力をトリムして返す。EOF時はnil。
    private static func promptInput(_ message: String) -> String? {
        print(message, terminator: "")
        fflush(stdout)
        guard let line = readLine() else {
            return nil
        }
        return line.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
