import Foundation

/// コマンドラインの引数解析や実行時に発生するエラー種別を表す。
public enum CLIError: Error, LocalizedError, Sendable {
    case invalidUsage(String)
    case runtime(String)

    public var errorDescription: String? {
        switch self {
        case .invalidUsage(let message), .runtime(let message):
            return message
        }
    }

    /// 終了コード（引数誤りは2、実行時エラーは1）を返す。
    public var exitCode: Int32 {
        switch self {
        case .invalidUsage:
            return 2
        case .runtime:
            return 1
        }
    }
}

/// 標準エラー出力へUTF-8のログ行を書き出す。
public func logStderr(_ message: String) {
    let data = Data((message + "\n").utf8)
    FileHandle.standardError.write(data)
}

/// `--key value` と `--key=value` の両形式を受け付ける軽量な引数パーサ。
public struct CLIArgumentParser: Sendable {
    private let args: [String]
    private var index: Int = 0

    public init(arguments: [String]) {
        self.args = arguments
    }

    /// 未処理の引数が残っているかを返す。
    public var hasNext: Bool {
        index < args.count
    }

    /// 次のトークンを取り出して進める。
    public mutating func nextToken() -> String? {
        guard index < args.count else { return nil }
        defer { index += 1 }
        return args[index]
    }

    /// オプションの値を、`=`付き形式または次のトークンから取得する。
    public mutating func nextValue(for option: String, inlineValue: String?) throws -> String {
        if let inlineValue {
            guard !inlineValue.isEmpty else {
                throw CLIError.invalidUsage("\(option) の値が空です。")
            }
            return inlineValue
        }
        guard let value = nextToken(), !value.isEmpty else {
            throw CLIError.invalidUsage("\(option) に値が指定されていません。")
        }
        return value
    }

    /// `--name=value` 形式のトークンをオプション名と値へ分解する。
    public static func splitOption(_ token: String) -> (name: String, inlineValue: String?) {
        guard token.hasPrefix("--"), let equalIndex = token.firstIndex(of: "=") else {
            return (token, nil)
        }
        let name = String(token[..<equalIndex])
        let valueStart = token.index(after: equalIndex)
        return (name, String(token[valueStart...]))
    }
}
