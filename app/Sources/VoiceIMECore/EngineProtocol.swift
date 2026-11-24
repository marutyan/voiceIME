import Foundation

/// 認識エンジンの整形モード。
public enum FormatMode: String, Codable, Sendable, Equatable {
    /// ASR出力を整形LLMで整形した結果を返す。
    case formatted
    /// 整形を行わずASR出力をそのまま返す。
    case raw
}

/// 録音開始時点の前面アプリ情報。`start`メッセージでエンジンへ渡す。
public struct TargetAppInfo: Codable, Sendable, Equatable {
    public let bundleId: String
    public let name: String

    enum CodingKeys: String, CodingKey {
        case bundleId = "bundle_id"
        case name
    }

    public init(bundleId: String, name: String) {
        self.bundleId = bundleId
        self.name = name
    }
}

/// `start` メッセージに載せる画面テキスト（`screen_text`）の整形と上限管理を一元化するヘルパー。
public enum EngineScreenText {
    /// `docs/engine-protocol.md` で定められた `screen_text` の最大文字数。
    public static let maxLength = 4_000

    /// OCRで得た行一覧から空行を除いて改行でつなぎ、最大文字数までに切り詰める。
    /// 有効な文字が残らない場合は `nil` を返す。
    public static func format(lines: [String], maxLength: Int = maxLength) -> String? {
        guard maxLength > 0 else { return nil }
        let nonEmptyLines = lines
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard !nonEmptyLines.isEmpty else { return nil }
        return truncateAndClean(nonEmptyLines.joined(separator: "\n"), maxLength: maxLength)
    }

    /// 送信直前の `screen_text` を正規化する。空または空白のみなら `nil` を返し、上限超過分は切り詰める。
    public static func normalize(_ text: String?, maxLength: Int = maxLength) -> String? {
        guard maxLength > 0, let text else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return truncateAndClean(trimmed, maxLength: maxLength)
    }

    private static func truncateAndClean(_ text: String, maxLength: Int) -> String? {
        let truncated = text.count <= maxLength ? text : String(text.prefix(maxLength))
        let cleaned = truncated.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? nil : cleaned
    }
}

/// アプリから認識エンジンへ標準入力で送る1行JSONメッセージ。
public enum EngineCommand: Sendable, Equatable {
    case start(sessionId: String, app: TargetAppInfo, screenText: String? = nil)
    case segment(sessionId: String, seq: Int, wavPath: String)
    case finish(sessionId: String, mode: FormatMode)
    case cancel(sessionId: String)
    case shutdown
}

extension EngineCommand: Encodable {
    private enum CodingKeys: String, CodingKey {
        case type
        case sessionId = "session_id"
        case app
        case screenText = "screen_text"
        case seq
        case wavPath = "wav_path"
        case mode
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case let .start(sessionId, app, screenText):
            try container.encode("start", forKey: .type)
            try container.encode(sessionId, forKey: .sessionId)
            try container.encode(app, forKey: .app)
            if let normalizedScreenText = EngineScreenText.normalize(screenText) {
                try container.encode(normalizedScreenText, forKey: .screenText)
            }
        case let .segment(sessionId, seq, wavPath):
            try container.encode("segment", forKey: .type)
            try container.encode(sessionId, forKey: .sessionId)
            try container.encode(seq, forKey: .seq)
            try container.encode(wavPath, forKey: .wavPath)
        case let .finish(sessionId, mode):
            try container.encode("finish", forKey: .type)
            try container.encode(sessionId, forKey: .sessionId)
            try container.encode(mode, forKey: .mode)
        case let .cancel(sessionId):
            try container.encode("cancel", forKey: .type)
            try container.encode(sessionId, forKey: .sessionId)
        case .shutdown:
            try container.encode("shutdown", forKey: .type)
        }
    }
}

/// エンジン起動完了通知（`ready`）の内容。
public struct EngineReadyEvent: Codable, Sendable, Equatable {
    public let asr: String?
    public let formatter: String?

    public init(asr: String? = nil, formatter: String? = nil) {
        self.asr = asr
        self.formatter = formatter
    }
}

/// 区間ごとの途中認識結果（`partial`）の内容。
public struct EnginePartialEvent: Codable, Sendable, Equatable {
    public let sessionId: String
    public let seq: Int
    public let text: String

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case seq
        case text
    }

    public init(sessionId: String, seq: Int, text: String) {
        self.sessionId = sessionId
        self.seq = seq
        self.text = text
    }
}

/// `finish`に対する最終結果（`result`）の内容。
public struct EngineResultEvent: Codable, Sendable, Equatable {
    public let sessionId: String
    public let rawText: String?
    public let text: String
    public let formatOk: Bool
    public let asrLatencyS: Double?
    public let formatLatencyS: Double?
    public let totalLatencyS: Double?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case rawText = "raw_text"
        case text
        case formatOk = "format_ok"
        case asrLatencyS = "asr_latency_s"
        case formatLatencyS = "format_latency_s"
        case totalLatencyS = "total_latency_s"
    }

    public init(
        sessionId: String,
        rawText: String?,
        text: String,
        formatOk: Bool,
        asrLatencyS: Double? = nil,
        formatLatencyS: Double? = nil,
        totalLatencyS: Double? = nil
    ) {
        self.sessionId = sessionId
        self.rawText = rawText
        self.text = text
        self.formatOk = formatOk
        self.asrLatencyS = asrLatencyS
        self.formatLatencyS = formatLatencyS
        self.totalLatencyS = totalLatencyS
    }
}

/// エンジンからのエラー通知（`error`）の内容。`rawText`がある場合はフォールバック貼り付けに使う。
public struct EngineErrorEvent: Codable, Sendable, Equatable {
    public let sessionId: String?
    public let message: String
    public let rawText: String?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case message
        case rawText = "raw_text"
    }

    public init(sessionId: String?, message: String, rawText: String? = nil) {
        self.sessionId = sessionId
        self.message = message
        self.rawText = rawText
    }
}

/// 認識エンジンから標準出力で受け取る1行JSONメッセージ。
public enum EngineEvent: Sendable, Equatable {
    case ready(EngineReadyEvent)
    case partial(EnginePartialEvent)
    case result(EngineResultEvent)
    case error(EngineErrorEvent)
}

/// プロトコルJSONのデコード失敗理由。
public enum EngineProtocolError: Error, LocalizedError, Equatable, Sendable {
    case unknownEventType(String)
    case invalidUTF8

    public var errorDescription: String? {
        switch self {
        case let .unknownEventType(type):
            return "未知のエンジンイベント種別です: \(type)"
        case .invalidUTF8:
            return "エンジンメッセージのUTF-8変換に失敗しました。"
        }
    }
}

extension EngineEvent: Decodable {
    private enum TypeCodingKeys: String, CodingKey {
        case type
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: TypeCodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)
        switch type {
        case "ready":
            self = .ready(try EngineReadyEvent(from: decoder))
        case "partial":
            self = .partial(try EnginePartialEvent(from: decoder))
        case "result":
            self = .result(try EngineResultEvent(from: decoder))
        case "error":
            self = .error(try EngineErrorEvent(from: decoder))
        default:
            throw EngineProtocolError.unknownEventType(type)
        }
    }
}

/// JSONLメッセージのエンコード・デコードを一元化するヘルパー。
public enum EngineProtocolCodec {
    /// コマンドを末尾改行付きの1行UTF-8 JSONへ変換する。
    public static func encodeLine(_ command: EngineCommand) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.withoutEscapingSlashes, .sortedKeys]
        var data = try encoder.encode(command)
        data.append(0x0A) // '\n'
        return data
    }

    /// 1行分のUTF-8 JSONデータを`EngineEvent`へ変換する。
    public static func decodeLine(_ data: Data) throws -> EngineEvent {
        let decoder = JSONDecoder()
        return try decoder.decode(EngineEvent.self, from: data)
    }
}
