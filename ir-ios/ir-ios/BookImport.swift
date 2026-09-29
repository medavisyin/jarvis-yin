import Foundation
import PDFKit

enum BookImport {
    static let unknown = "无法识别这个文件"
    static let failed = "这本书无法导入"

    static func chunks(name: String?, mime: String?, data: Data) throws -> (kind: String, chunks: [String]) {
        guard let kind = FileKind.detect(name: name, mime: mime) else {
            throw ImportFailure(unknown)
        }
        let chunks: [String]
        switch kind {
        case "txt":
            guard let text = String(data: data, encoding: .utf8) else { throw ImportFailure(failed) }
            chunks = Chunker.chunk(text.trimmingCharacters(in: .whitespacesAndNewlines), maxWords: 400)
        case "epub":
            chunks = try Chunker.chunk(EpubText.extract(data), maxWords: 400)
        case "pdf":
            chunks = Chunker.chunk(try pdfText(data), maxWords: 400)
        default:
            throw ImportFailure(unknown)
        }
        if let error = BookOpen.errorIfEmpty(chunks) { throw ImportFailure(error) }
        return (kind, chunks)
    }

    private static func pdfText(_ data: Data) throws -> String {
        guard let document = PDFDocument(data: data) else { throw ImportFailure(failed) }
        var pages: [String] = []
        for index in 0..<document.pageCount {
            let page = document.page(at: index)?.string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !page.isEmpty { pages.append(page) }
        }
        let text = pages.joined(separator: "\n\n")
        if text.isEmpty { throw ImportFailure(failed) }
        return text
    }
}
