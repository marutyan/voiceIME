import CoreFoundation
import Foundation

// ASR文を元の表記と読みの組に分ける。未変換の空白・記号も残し、Pythonで元の文字位置を復元できるようにする。
func tokenize(_ text: String) -> [[String]] {
    let source = text as NSString
    let mode = kCFStringTokenizerAttributeLatinTranscription
    let scanner = CFStringTokenizerCreate(
        nil, text as CFString, CFRangeMake(0, source.length),
        kCFStringTokenizerUnitWord | mode, Locale(identifier: "ja_JP") as CFLocale
    )!
    var tokens: [[String]] = []
    var end = 0
    while !CFStringTokenizerAdvanceToNextToken(scanner).isEmpty {
        let range = CFStringTokenizerGetCurrentTokenRange(scanner)
        if end < range.location {
            tokens.append([source.substring(with: NSRange(location: end, length: range.location - end)), ""])
        }
        let raw = source.substring(with: NSRange(location: range.location, length: range.length))
        let hasKanji = raw.unicodeScalars.contains { (0x3400...0x9fff).contains($0.value) || $0.value == 0x3005 }
        let latin = hasKanji ? CFStringTokenizerCopyCurrentTokenAttribute(scanner, mode) as? String : nil
        let kana = latin?.applyingTransform(.latinToKatakana, reverse: false) ?? ""
        tokens.append([raw, kana])
        end = range.location + range.length
    }
    if end < source.length {
        tokens.append([source.substring(from: end), ""])
    }
    return tokens
}

let decoder = JSONDecoder()
let encoder = JSONEncoder()
while let line = readLine() {
    let texts = try decoder.decode([String].self, from: Data(line.utf8))
    let data = try encoder.encode(texts.map(tokenize))
    print(String(decoding: data, as: UTF8.self))
}
