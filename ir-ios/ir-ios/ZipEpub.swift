import Foundation

enum RawInflate {
    static func inflate(_ data: Data) -> Data? {
        if data.isEmpty { return Data() }
        return data.withUnsafeBytes { buffer in
            guard let base = buffer.bindMemory(to: UInt8.self).baseAddress else { return nil }
            var outLen = 0
            guard let ptr = ir_inflate_raw(base, buffer.count, &outLen) else { return nil }
            defer { ir_free(ptr) }
            return Data(bytes: ptr, count: outLen)
        }
    }

    static func deflate(_ data: Data) -> Data? {
        if data.isEmpty { return Data() }
        return data.withUnsafeBytes { buffer in
            guard let base = buffer.bindMemory(to: UInt8.self).baseAddress else { return nil }
            var outLen = 0
            guard let ptr = ir_deflate_raw(base, buffer.count, &outLen) else { return nil }
            defer { ir_free(ptr) }
            return Data(bytes: ptr, count: outLen)
        }
    }
}

enum ZipArchive {
    static func files(in data: Data) throws -> [String: Data] {
        let bytes = [UInt8](data)
        guard let eocd = findEOCD(bytes) else { throw ImportFailure("这本书无法导入") }
        let count = int16(bytes, eocd + 10)
        var cursor = int32(bytes, eocd + 16)
        var files: [String: Data] = [:]
        for _ in 0..<count {
            guard cursor + 46 <= bytes.count, UInt32(little32(bytes, cursor)) == 0x02014b50 else {
                throw ImportFailure("这本书无法导入")
            }
            let method = int16(bytes, cursor + 10)
            let compressedSize = int32(bytes, cursor + 20)
            let nameLen = int16(bytes, cursor + 28)
            let extraLen = int16(bytes, cursor + 30)
            let commentLen = int16(bytes, cursor + 32)
            let localOffset = int32(bytes, cursor + 42)
            let nameStart = cursor + 46
            let nameEnd = nameStart + nameLen
            guard nameEnd <= bytes.count else { throw ImportFailure("这本书无法导入") }
            let name = decodeName(Data(bytes[nameStart..<nameEnd]))
            cursor = nameEnd + extraLen + commentLen
            if name.hasSuffix("/") { continue }
            files[name] = try entryData(bytes, localOffset: localOffset, method: method, compressedSize: compressedSize)
        }
        return files
    }

    private static func entryData(_ bytes: [UInt8], localOffset: Int, method: Int, compressedSize: Int) throws -> Data {
        guard localOffset + 30 <= bytes.count, UInt32(little32(bytes, localOffset)) == 0x04034b50 else {
            throw ImportFailure("这本书无法导入")
        }
        let nameLen = int16(bytes, localOffset + 26)
        let extraLen = int16(bytes, localOffset + 28)
        let start = localOffset + 30 + nameLen + extraLen
        let end = start + compressedSize
        guard start >= 0, end <= bytes.count else { throw ImportFailure("这本书无法导入") }
        let payload = Data(bytes[start..<end])
        switch method {
        case 0:
            return payload
        case 8:
            guard let inflated = RawInflate.inflate(payload) else { throw ImportFailure("这本书无法导入") }
            return inflated
        default:
            throw ImportFailure("这本书无法导入")
        }
    }

    private static func findEOCD(_ bytes: [UInt8]) -> Int? {
        if bytes.count < 22 { return nil }
        let minStart = max(0, bytes.count - 22 - 65535)
        var index = bytes.count - 22
        while index >= minStart {
            if bytes[index] == 0x50, bytes[index + 1] == 0x4b, bytes[index + 2] == 0x05, bytes[index + 3] == 0x06 {
                return index
            }
            index -= 1
        }
        return nil
    }

    private static func little32(_ bytes: [UInt8], _ offset: Int) -> Int {
        Int(bytes[offset]) | (Int(bytes[offset + 1]) << 8) | (Int(bytes[offset + 2]) << 16) | (Int(bytes[offset + 3]) << 24)
    }

    private static func int16(_ bytes: [UInt8], _ offset: Int) -> Int {
        Int(bytes[offset]) | (Int(bytes[offset + 1]) << 8)
    }

    private static func int32(_ bytes: [UInt8], _ offset: Int) -> Int {
        little32(bytes, offset)
    }

    private static func decodeName(_ data: Data) -> String {
        String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) ?? ""
    }
}

enum HtmlText {
    static func paragraphs(_ html: String) -> String {
        var source = html
        source = replacing(source, #"<(?i:script|style)\b[^>]*>[\s\S]*?</(?i:script|style)>"#, with: " ")
        source = replacing(source, #"(?i)<br\s*/?>"#, with: "\n")
        source = replacing(source, #"(?i)</(p|div|h[1-6]|li|tr|blockquote)>"#, with: "\n\n")
        source = replacing(source, #"<[^>]+>"#, with: "")
        source = decode(source)
        let blocks = source.components(separatedBy: "\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return blocks.joined(separator: "\n\n")
    }

    static func firstHeading(_ html: String) -> String {
        guard let range = html.range(of: #"(?is)<h[1-3]\b[^>]*>(.*?)</h[1-3]>"#, options: .regularExpression) else {
            return ""
        }
        let tag = String(html[range])
        guard let open = tag.range(of: ">"), let close = tag.range(of: "</", options: .backwards) else { return "" }
        return paragraphs(String(tag[open.upperBound..<close.lowerBound])).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func replacing(_ text: String, _ pattern: String, with template: String) -> String {
        text.replacingOccurrences(of: pattern, with: template, options: .regularExpression)
    }

    private static func decode(_ text: String) -> String {
        var result = text
        let named = ["&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": "\"", "&apos;": "'"]
        for (entity, value) in named { result = result.replacingOccurrences(of: entity, with: value) }
        result = decodeNumeric(result, pattern: #"&#(\d+);"#, hex: false)
        result = decodeNumeric(result, pattern: #"&#x([0-9a-fA-F]+);"#, hex: true)
        return result
    }

    private static func decodeNumeric(_ text: String, pattern: String, hex: Bool) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
        let ns = text as NSString
        var output = text
        let matches = regex.matches(in: text, range: NSRange(location: 0, length: ns.length)).reversed()
        for match in matches {
            guard let full = Range(match.range, in: output), let digits = Range(match.range(at: 1), in: output) else { continue }
            let raw = String(output[digits])
            let scalar = hex ? Int(raw, radix: 16) : Int(raw)
            if let scalar, let uni = UnicodeScalar(scalar) {
                output.replaceSubrange(full, with: String(Character(uni)))
            }
        }
        return output
    }
}

enum EpubText {
    static func extract(_ data: Data) throws -> String {
        let files = try ZipArchive.files(in: data)
        let container = files.first { $0.key.hasSuffix("META-INF/container.xml") }?.value
        guard let container, let xml = String(data: container, encoding: .utf8) else {
            throw ImportFailure("这本书无法导入")
        }
        guard let root = firstAttr(xml, "full-path"), let opfData = files[root] ?? files.first(where: { $0.key.hasSuffix(root) })?.value,
              let opf = String(data: opfData, encoding: .utf8) else {
            throw ImportFailure("这本书无法导入")
        }
        let opfDir = root.split(separator: "/").dropLast().joined(separator: "/")
        let prefix = opfDir.isEmpty ? "" : opfDir + "/"
        let hrefById = manifest(opf)
        let spine = itemrefs(opf).compactMap { hrefById[$0] }
        let hrefs = spine.isEmpty ? hrefById.values.sorted() : spine
        let parts = hrefs.compactMap { href -> String? in
            let path = prefix + href
            let bytes = files[path] ?? files.first { $0.key.hasSuffix(href) }?.value
            guard let bytes, let html = String(data: bytes, encoding: .utf8) else { return nil }
            let text = HtmlText.paragraphs(html)
            return text.isEmpty ? nil : text
        }
        let joined = parts.joined(separator: "\n\n")
        if joined.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw ImportFailure("这本书无法导入")
        }
        return joined
    }

    private static func firstAttr(_ xml: String, _ name: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: name + #"\s*=\s*"([^"]+)""#) else { return nil }
        let range = NSRange(xml.startIndex..., in: xml)
        guard let match = regex.firstMatch(in: xml, range: range), let value = Range(match.range(at: 1), in: xml) else { return nil }
        return String(xml[value])
    }

    private static func manifest(_ opf: String) -> [String: String] {
        guard let regex = try? NSRegularExpression(pattern: #"<item\b[^>]*>"#, options: [.caseInsensitive]) else { return [:] }
        var map: [String: String] = [:]
        for match in regex.matches(in: opf, range: NSRange(opf.startIndex..., in: opf)) {
            guard let range = Range(match.range, in: opf) else { continue }
            let tag = String(opf[range])
            if let id = firstAttr(tag, "id"), let href = firstAttr(tag, "href") {
                map[id] = href.removingPercentEncoding ?? href
            }
        }
        return map
    }

    private static func itemrefs(_ opf: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: #"<itemref\b[^>]*>"#, options: [.caseInsensitive]) else { return [] }
        return regex.matches(in: opf, range: NSRange(opf.startIndex..., in: opf)).compactMap { match in
            guard let range = Range(match.range, in: opf) else { return nil }
            return firstAttr(String(opf[range]), "idref")
        }
    }
}

struct ImportFailure: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}
