import Foundation

enum FileKind {
    static func detect(name: String?, mime: String?) -> String? {
        let trimmed = name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if let dot = trimmed.lastIndex(of: "."), dot != trimmed.startIndex, trimmed.index(after: dot) != trimmed.endIndex {
            switch trimmed[trimmed.index(after: dot)...].lowercased() {
            case "txt": return "txt"
            case "epub": return "epub"
            case "pdf": return "pdf"
            default: return nil
            }
        }
        let base = mime?.split(separator: ";", maxSplits: 1).first.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() } ?? ""
        switch base {
        case "text/plain": return "txt"
        case "application/epub+zip": return "epub"
        case "application/pdf": return "pdf"
        default: return nil
        }
    }
}

enum Chunker {
    static func wordCount(_ text: String) -> Int {
        let spaced = text.split { $0.isWhitespace }.count
        let cjk = text.unicodeScalars.filter { (0x4E00...0x9FFF).contains($0.value) }.count
        if cjk > spaced * 2 { return max(cjk, spaced) }
        return spaced
    }

    static func chunk(_ text: String, maxWords: Int = 1200) -> [String] {
        let blocks = text.split(separator: /\n\s*\n/)
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if blocks.isEmpty { return [] }
        let pieces = blocks.flatMap { splitToFit($0, maxWords: maxWords) }
        return pack(pieces, maxWords: maxWords, separator: "\n\n")
    }

    private static func splitToFit(_ para: String, maxWords: Int) -> [String] {
        if wordCount(para) <= maxWords { return [para] }
        let sentences = splitSentences(para)
        if sentences.count <= 1 { return splitWords(para, maxWords: maxWords) }
        return pack(sentences, maxWords: maxWords, separator: " ").flatMap { piece in
            wordCount(piece) <= maxWords ? [piece] : splitWords(piece, maxWords: maxWords)
        }
    }

    private static func splitSentences(_ para: String) -> [String] {
        var parts: [String] = []
        var current = ""
        let chars = Array(para)
        var index = 0
        while index < chars.count {
            let ch = chars[index]
            current.append(ch)
            let isEnd = ch == "." || ch == "!" || ch == "?" || ch == "。" || ch == "！" || ch == "？"
            if isEnd {
                if ch == "." || ch == "!" || ch == "?" {
                    var next = index + 1
                    while next < chars.count, chars[next].isWhitespace {
                        current.append(chars[next])
                        next += 1
                    }
                    index = next
                } else {
                    index += 1
                }
                let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { parts.append(trimmed) }
                current = ""
                continue
            }
            index += 1
        }
        let tail = current.trimmingCharacters(in: .whitespacesAndNewlines)
        if !tail.isEmpty { parts.append(tail) }
        return parts
    }

    private static func splitWords(_ text: String, maxWords: Int) -> [String] {
        let words = text.split { $0.isWhitespace }.map(String.init)
        if words.isEmpty { return [] }
        let size = max(maxWords, 1)
        if words.count == 1, wordCount(words[0]) > size {
            return stride(from: 0, to: words[0].count, by: size).map { offset in
                let start = words[0].index(words[0].startIndex, offsetBy: offset)
                let end = words[0].index(start, offsetBy: size, limitedBy: words[0].endIndex) ?? words[0].endIndex
                return String(words[0][start..<end])
            }
        }
        return stride(from: 0, to: words.count, by: size).map { offset in
            words[offset..<min(offset + size, words.count)].joined(separator: " ")
        }
    }

    private static func pack(_ pieces: [String], maxWords: Int, separator: String) -> [String] {
        var chunks: [String] = []
        var current: [String] = []
        var words = 0
        for piece in pieces {
            let pieceWords = wordCount(piece)
            if !current.isEmpty, words + pieceWords > maxWords {
                chunks.append(current.joined(separator: separator))
                current.removeAll()
                words = 0
            }
            current.append(piece)
            words += pieceWords
        }
        if !current.isEmpty { chunks.append(current.joined(separator: separator)) }
        return chunks
    }
}

enum ChapterLabels {
    static func label(title: String, index: Int) -> String {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { return trimmed }
        return "第 \(index + 1) 段"
    }
}

enum BookOpen {
    static func errorIfEmpty(_ chunks: [String]) -> String? {
        chunks.isEmpty ? "这本书无法导入" : nil
    }
}

struct WordHit: Equatable {
    var word: String
    var sentence: String
    var start: Int
    var end: Int
}

enum WordSelector {
    static func at(text: String, index: Int) -> WordHit? {
        let chars = Array(text)
        if index < 0 || index >= chars.count { return nil }
        return span(chars: chars, anchor: index, focus: index)
    }

    static func span(text: String, anchor: Int, focus: Int) -> WordHit? {
        span(chars: Array(text), anchor: anchor, focus: focus)
    }

    private static func span(chars: [Character], anchor: Int, focus: Int) -> WordHit? {
        if chars.isEmpty { return nil }
        let anchorIndex = min(max(anchor, 0), chars.count - 1)
        if !chars[anchorIndex].isLetter { return nil }
        let focusIndex = min(max(focus, 0), chars.count - 1)
        let endIndex: Int
        if chars[focusIndex].isLetter {
            endIndex = focusIndex
        } else if let nearest = nearestLetter(chars, from: focusIndex, toward: anchorIndex) {
            endIndex = nearest
        } else {
            endIndex = anchorIndex
        }
        guard let anchorBounds = wordBounds(chars, index: anchorIndex),
              let endBounds = wordBounds(chars, index: endIndex) else { return nil }
        let from = min(anchorBounds.lowerBound, endBounds.lowerBound)
        let to = max(anchorBounds.upperBound, endBounds.upperBound)
        let word = String(chars[from..<to]).trimmingCharacters(in: .whitespacesAndNewlines)
        if word.isEmpty { return nil }
        return WordHit(word: word, sentence: sentenceContaining(chars, index: from), start: from, end: to)
    }

    private static func nearestLetter(_ chars: [Character], from: Int, toward: Int) -> Int? {
        let step = toward < from ? -1 : 1
        var index = from
        while index != toward {
            if chars[index].isLetter { return index }
            index += step
        }
        return chars[toward].isLetter ? toward : nil
    }

    private static func wordBounds(_ chars: [Character], index: Int) -> Range<Int>? {
        if !chars[index].isLetter { return nil }
        var start = index
        while start > 0, chars[start - 1].isLetter { start -= 1 }
        var end = index
        while end + 1 < chars.count, chars[end + 1].isLetter { end += 1 }
        return start..<(end + 1)
    }

    private static func sentenceContaining(_ chars: [Character], index: Int) -> String {
        var from = index
        while from > 0 {
            let previous = chars[from - 1]
            if previous == "." || previous == "?" || previous == "!" { break }
            from -= 1
        }
        while from < chars.count, chars[from].isWhitespace { from += 1 }
        var to = index
        while to < chars.count, chars[to] != ".", chars[to] != "?", chars[to] != "!" { to += 1 }
        if to < chars.count { to += 1 }
        return String(chars[from..<to]).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

struct Sense: Equatable {
    var id: Int
    var pos: String?
    var translation: String
}

enum SenseParser {
    private static let numbered = try! NSRegularExpression(pattern: #"^\s*\d+\.\s*"#)
    private static let posPrefix = try! NSRegularExpression(
        pattern: #"^(n|v|vt|vi|adj|adv|prep|conj|pron|art|num|int|aux)\.\s+"#,
        options: [.caseInsensitive]
    )

    static func parse(translation: String, posField: String?) -> [Sense] {
        _ = posField
        let lines = translation.split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && !isHiddenLine($0) }
        return lines.enumerated().map { idx, raw in
            let unnumbered = numbered.stringByReplacingMatches(
                in: raw,
                range: NSRange(raw.startIndex..., in: raw),
                withTemplate: ""
            )
            let range = NSRange(unnumbered.startIndex..., in: unnumbered)
            if let match = posPrefix.firstMatch(in: unnumbered, range: range),
               let posRange = Range(match.range(at: 1), in: unnumbered),
               let whole = Range(match.range, in: unnumbered) {
                let pos = String(unnumbered[posRange]).lowercased()
                let text = unnumbered[whole.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)
                return Sense(id: idx, pos: pos, translation: text)
            }
            return Sense(id: idx, pos: nil, translation: unnumbered.trimmingCharacters(in: .whitespacesAndNewlines))
        }
    }

    private static func isHiddenLine(_ line: String) -> Bool {
        if line.range(of: #"^\[时态\]"#, options: .regularExpression) != nil { return true }
        return line.range(of: #"^\([^()\n]*\d+/\d+[^()\n]*\)$"#, options: .regularExpression) != nil
    }
}

struct LemmaMap {
    private let inflectedToStem: [String: String]

    init(inflectedToStem: [String: String]) {
        self.inflectedToStem = inflectedToStem
    }

    func stem(_ word: String) -> String {
        let key = word.lowercased()
        return inflectedToStem[key] ?? key
    }

    static func load(_ text: String) -> LemmaMap {
        var map: [String: String] = [:]
        for lineSub in text.split(whereSeparator: \.isNewline) {
            let trimmed = lineSub.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty || trimmed.hasPrefix(";") { continue }
            let parts = trimmed.split(separator: "->", maxSplits: 1, omittingEmptySubsequences: false).map(String.init)
            if parts.count != 2 { continue }
            let stem = parts[0].split(separator: "/", maxSplits: 1).first
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() } ?? ""
            if stem.isEmpty { continue }
            map[stem] = stem
            for form in parts[1].split(separator: ",") {
                let key = form.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                if !key.isEmpty { map[key] = stem }
            }
        }
        return LemmaMap(inflectedToStem: map)
    }
}

struct DictRow: Equatable {
    var word: String
    var pos: String?
    var translation: String
}

struct DictHit: Equatable {
    var word: String
    var senses: [Sense]
}

struct DictionaryRepository {
    var lemma: LemmaMap
    var lookupExact: (String) -> DictRow?

    func lookup(_ raw: String) -> DictHit? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        let stem = lemma.stem(trimmed)
        guard let row = lookupExact(stem) ?? lookupExact(trimmed.lowercased()) else { return nil }
        let senses = SenseParser.parse(translation: row.translation, posField: row.pos)
        if senses.isEmpty { return nil }
        return DictHit(word: row.word, senses: senses)
    }
}

enum ExplainStatus {
    case ok
    case notInDict
}

struct ExplainCard: Equatable {
    var status: ExplainStatus
    var word: String = ""
    var translation: String = ""
    var example: String = ""
}

enum ExplainPipeline {
    static func dictionaryCard(selected: String, sentence: String, dict: DictionaryRepository?) -> ExplainCard {
        guard let dict, let hit = dict.lookup(selected) else {
            return ExplainCard(status: .notInDict, word: selected, example: sentence)
        }
        let translation = hit.senses.map { sense in
            [sense.pos, sense.translation].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " ")
        }.joined(separator: "\n")
        return ExplainCard(status: .ok, word: hit.word, translation: translation, example: sentence)
    }
}

enum GlossPrompt {
    static func isPhrase(_ selected: String) -> Bool {
        selected.trimmingCharacters(in: .whitespacesAndNewlines).split { $0.isWhitespace }.count > 1
    }

    static func user(word: String, sentence: String) -> String {
        """
        句子：\(sentence)
        「\(word)」在这句里是什么意思？只写一句中文，不要写英文。
        中文：
        """
    }

    static func userRetry(word: String, sentence: String) -> String {
        """
        句子：\(sentence)
        用汉字说明「\(word)」的意思。不要写英文。
        中文：
        """
    }

    static func phraseMeaning(_ phrase: String) -> String {
        """
        词组：\(phrase)
        这个词组本身是什么意思？只写一句中文，不要英文，不要举例。
        中文：
        """
    }

    static func phraseMeaningRetry(_ phrase: String) -> String {
        """
        词组：\(phrase)
        用汉字解释这个词组。不要写英文。
        中文：
        """
    }

    static func translation(_ sentence: String) -> String {
        """
        \(sentence)
        把上一句翻译成中文。只写中文，不要写英文。
        中文：
        """
    }

    static func translationRetry(_ sentence: String) -> String {
        """
        \(sentence)
        用汉字翻译上面这句。
        中文：
        """
    }
}

enum GlossText {
    static func sentence(_ raw: String) -> String {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let end = text.range(of: "</think>", options: .backwards) {
            text = String(text[end.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
        } else if text.hasPrefix("<think>") {
            return ""
        }
        if text.hasPrefix("中文：") { text = String(text.dropFirst("中文：".count)) }
        else if text.hasPrefix("中文:") { text = String(text.dropFirst("中文:".count)) }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func chinese(_ raw: String) -> String {
        let text = sentence(raw)
        guard let first = text.unicodeScalars.firstIndex(where: { (0x4E00...0x9FFF).contains($0.value) }) else {
            return ""
        }
        return String(text[first...]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func firstSentence(_ text: String) -> String {
        var end = text.startIndex
        for ch in text {
            end = text.index(after: end)
            if ch == "。" || ch == "！" || ch == "？" || ch == "\n" { break }
        }
        return String(text[..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

protocol QwenEngine: AnyObject {
    func complete(prompt: String, maxTokens: Int) async throws -> String
}

enum QwenCopy {
    static let notConnected = "Qwen 还没接到这台手机上"
    static let wordFailed = "这个词没解释成中文"
    static let sentenceFailed = "这句没译成中文"
}

struct GlossSession {
    var engine: QwenEngine?

    func word(selected: String, sentence: String) async -> String {
        if GlossPrompt.isPhrase(selected) {
            return await run(
                prompt: GlossPrompt.phraseMeaning(selected),
                retry: GlossPrompt.phraseMeaningRetry(selected),
                maxTokens: 80,
                empty: QwenCopy.wordFailed,
                keepFirstSentence: true
            )
        }
        return await run(
            prompt: GlossPrompt.user(word: selected, sentence: sentence),
            retry: GlossPrompt.userRetry(word: selected, sentence: sentence),
            maxTokens: 80,
            empty: QwenCopy.wordFailed,
            keepFirstSentence: true
        )
    }

    func sentence(_ sentence: String) async -> String {
        await run(
            prompt: GlossPrompt.translation(sentence),
            retry: GlossPrompt.translationRetry(sentence),
            maxTokens: 120,
            empty: QwenCopy.sentenceFailed,
            keepFirstSentence: false
        )
    }

    private func run(prompt: String, retry: String, maxTokens: Int, empty: String, keepFirstSentence: Bool) async -> String {
        guard let engine else { return QwenCopy.notConnected }
        let first = (try? await engine.complete(prompt: prompt, maxTokens: maxTokens)) ?? ""
        var text = GlossText.chinese(first)
        if text.isEmpty {
            let second = (try? await engine.complete(prompt: retry, maxTokens: maxTokens)) ?? ""
            text = GlossText.chinese(second)
        }
        if text.isEmpty { return empty }
        return keepFirstSentence ? GlossText.firstSentence(text) : text
    }
}
