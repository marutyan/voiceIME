import Foundation

/// manifest各行の `glossary` に含まれる用語エントリを表す。
public struct GlossaryEntry: Codable, Sendable, Equatable {
    public let surface: String
    public let reading: String?

    public init(surface: String, reading: String? = nil) {
        self.surface = surface
        self.reading = reading
    }
}

/// `apple-transcribe` が入力manifestから読み取る発話レコード。
public struct TranscribeManifestEntry: Decodable, Sendable, Equatable {
    public let id: String
    public let audioPath: String
    public let glossary: [GlossaryEntry]?

    enum CodingKeys: String, CodingKey {
        case id
        case audioPath = "audio_path"
        case glossary
    }

    public init(id: String, audioPath: String, glossary: [GlossaryEntry]? = nil) {
        self.id = id
        self.audioPath = audioPath
        self.glossary = glossary
    }

    /// 認識ヒントへ渡す重複なしの表記一覧を、元の順序を保って返す。
    public func glossarySurfaces() -> [String] {
        guard let glossary else { return [] }
        var seen = Set<String>()
        var result: [String] = []
        for item in glossary {
            let trimmed = item.surface.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }
            if seen.insert(trimmed).inserted {
                result.append(trimmed)
            }
        }
        return result
    }
}

/// `apple-transcribe` が出力する推論結果の1行（計画書のJSONL形式）。
public struct TranscriptionResultRow: Codable, Sendable, Equatable {
    public let id: String
    public let system: String
    public let stage: String
    public let hyp: String
    public let latencySeconds: Double

    enum CodingKeys: String, CodingKey {
        case id
        case system
        case stage
        case hyp
        case latencySeconds = "latency_s"
    }

    public init(id: String, system: String, stage: String = "asr", hyp: String, latencySeconds: Double) {
        self.id = id
        self.system = system
        self.stage = stage
        self.hyp = hyp
        self.latencySeconds = latencySeconds
    }
}

/// 録音用プロンプトmanifestの1行。出力時に元の任意フィールドをそのまま引き継ぐため生JSONも保持する。
public struct PromptRow: @unchecked Sendable {
    public let id: String
    public let spokenText: String
    /// 入力JSONオブジェクトの複製。`JSONSerialization` 由来のため送信境界で書き換えない前提とする。
    public let rawObject: [String: Any]

    public init(id: String, spokenText: String, rawObject: [String: Any]) {
        self.id = id
        self.spokenText = spokenText
        self.rawObject = rawObject
    }
}

/// JSONL形式のmanifest読み書きとパス解決をまとめて担うユーティリティ。
public enum ManifestIO {
    /// 音声認識用のmanifest JSONLを読み込む。空行は無視し、行番号付きで形式誤りを報告する。
    public static func loadTranscribeManifest(from url: URL) throws -> [TranscribeManifestEntry] {
        let content: String
        do {
            content = try String(contentsOf: url, encoding: .utf8)
        } catch {
            throw CLIError.runtime("manifestを読み込めませんでした (\(url.path)): \(error.localizedDescription)")
        }

        let decoder = JSONDecoder()
        var entries: [TranscribeManifestEntry] = []
        let lines = content.split(omittingEmptySubsequences: false, whereSeparator: \.isNewline)
        for (idx, rawLine) in lines.enumerated() {
            let trimmed = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { continue }
            guard let data = trimmed.data(using: .utf8) else {
                throw CLIError.runtime("manifestの\(idx + 1)行目をUTF-8として解釈できません。")
            }
            do {
                let entry = try decoder.decode(TranscribeManifestEntry.self, from: data)
                entries.append(entry)
            } catch {
                throw CLIError.runtime("manifestの\(idx + 1)行目のJSON解析に失敗しました: \(error.localizedDescription)")
            }
        }
        return entries
    }

    /// `audio_path` を絶対パスまたはmanifestの親ディレクトリ基準（存在しなければカレント基準）で解決する。
    public static func resolveAudioURL(audioPath: String, manifestURL: URL) throws -> URL {
        let fm = FileManager.default
        if audioPath.hasPrefix("/") {
            let url = URL(fileURLWithPath: audioPath).standardizedFileURL
            guard fm.fileExists(atPath: url.path) else {
                throw CLIError.runtime("音声ファイルが見つかりません: \(url.path)")
            }
            return url
        }

        let manifestDir = manifestURL.standardizedFileURL.deletingLastPathComponent()
        let candidateInManifestDir = manifestDir.appendingPathComponent(audioPath).standardizedFileURL
        if fm.fileExists(atPath: candidateInManifestDir.path) {
            return candidateInManifestDir
        }

        let candidateInCwd = URL(fileURLWithPath: audioPath).standardizedFileURL
        if fm.fileExists(atPath: candidateInCwd.path) {
            return candidateInCwd
        }

        throw CLIError.runtime("音声ファイルが見つかりません: \(candidateInManifestDir.path)")
    }

    /// 任意の `Encodable` 値を1行のUTF-8 JSONLデータ（末尾改行付き）へ変換する。
    public static func encodeJSONLine<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.withoutEscapingSlashes]
        var data = try encoder.encode(value)
        data.append(0x0A)
        return data
    }

    /// 録音プロンプト用のJSONLを読み込み、必須項目（`id` と `spoken_text`）とIDの安全性を検証する。
    public static func loadPromptManifest(from url: URL) throws -> [PromptRow] {
        let content: String
        do {
            content = try String(contentsOf: url, encoding: .utf8)
        } catch {
            throw CLIError.runtime("prompts manifestを読み込めませんでした (\(url.path)): \(error.localizedDescription)")
        }

        var rows: [PromptRow] = []
        var seenIDs = Set<String>()
        let lines = content.split(omittingEmptySubsequences: false, whereSeparator: \.isNewline)

        for (idx, rawLine) in lines.enumerated() {
            let trimmed = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { continue }
            guard let data = trimmed.data(using: .utf8) else {
                throw CLIError.runtime("prompts manifestの\(idx + 1)行目をUTF-8として解釈できません。")
            }
            let jsonObj: Any
            do {
                jsonObj = try JSONSerialization.jsonObject(with: data)
            } catch {
                throw CLIError.runtime("prompts manifestの\(idx + 1)行目のJSON解析に失敗しました: \(error.localizedDescription)")
            }
            guard let dict = jsonObj as? [String: Any] else {
                throw CLIError.runtime("prompts manifestの\(idx + 1)行目がJSONオブジェクトではありません。")
            }
            guard let id = dict["id"] as? String, !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw CLIError.runtime("prompts manifestの\(idx + 1)行目に文字列の id がありません。")
            }
            // 音声ファイル名として使うため、パス区切りや親ディレクトリ参照を含むIDを拒否する。
            guard !id.contains("/"), !id.contains("\\"), id != ".", id != "..", !id.contains("..") else {
                throw CLIError.runtime("prompts manifestの\(idx + 1)行目の id にファイル名として使えない文字が含まれています: \(id)")
            }
            guard seenIDs.insert(id).inserted else {
                throw CLIError.runtime("prompts manifestの\(idx + 1)行目で重複した id が見つかりました: \(id)")
            }
            guard let spokenText = dict["spoken_text"] as? String, !spokenText.isEmpty else {
                throw CLIError.runtime("prompts manifestの\(idx + 1)行目に文字列の spoken_text がありません。")
            }
            rows.append(PromptRow(id: id, spokenText: spokenText, rawObject: dict))
        }
        return rows
    }

    /// 既存の出力manifestから録音済みの `id` 集合を読み取る。ファイルが存在しない場合は空集合を返す。
    public static func loadRecordedIDs(from manifestURL: URL) throws -> Set<String> {
        guard FileManager.default.fileExists(atPath: manifestURL.path) else {
            return []
        }
        let content = try String(contentsOf: manifestURL, encoding: .utf8)
        var ids = Set<String>()
        let lines = content.split(omittingEmptySubsequences: false, whereSeparator: \.isNewline)
        for (idx, rawLine) in lines.enumerated() {
            let trimmed = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { continue }
            guard let data = trimmed.data(using: .utf8),
                  let dict = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let id = dict["id"] as? String else {
                throw CLIError.runtime("既存の出力manifestの\(idx + 1)行目を解析できません (\(manifestURL.path))。")
            }
            ids.insert(id)
        }
        return ids
    }

    /// 録音済みの1件について、元の行の全フィールドを保ったまま録音メタデータを付与したJSONL行を作る。
    public static func buildRecordedManifestLine(prompt: PromptRow, relativeAudioPath: String, split: String = "test-user") throws -> Data {
        var merged = prompt.rawObject
        merged["audio_path"] = relativeAudioPath
        merged["speaker"] = "user"
        merged["source"] = "user"
        merged["split"] = split

        var data = try JSONSerialization.data(
            withJSONObject: merged,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        data.append(0x0A)
        return data
    }

    /// 出力ファイルへ1行を追記して即座にディスクへ同期する。途中終了でも確定分を失わないため。
    public static func appendLine(_ data: Data, to url: URL) throws {
        let fm = FileManager.default
        let parent = url.deletingLastPathComponent()
        try fm.createDirectory(at: parent, withIntermediateDirectories: true)
        if !fm.fileExists(atPath: url.path) {
            fm.createFile(atPath: url.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: data)
        try handle.synchronize()
    }
}
