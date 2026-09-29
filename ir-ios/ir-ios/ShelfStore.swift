import Foundation

struct ShelfEntry: Equatable, Identifiable {
    var id: String
    var title: String
    var kind: String
    var chunkIndex: Int
    var chunkCount: Int
    var updatedAt: Int64
}

final class ShelfStore {
    private let root: URL

    init(root: URL) {
        self.root = root
    }

    func list() -> [ShelfEntry] {
        readIndex().books.sorted { $0.updatedAt > $1.updatedAt }
    }

    func loadChunks(id: String) -> [String] { readBook(id).chunks }
    func loadTitles(id: String) -> [String] { readBook(id).titles }

    @discardableResult
    func save(title: String, kind: String, chunks: [String], titles: [String] = [], now: Int64 = ShelfStore.now()) -> ShelfEntry {
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let id = uniqueId(now)
        let aligned = (0..<chunks.count).map { index in index < titles.count ? titles[index] : "" }
        writeBook(id: id, chunks: chunks, titles: aligned)
        let entry = ShelfEntry(
            id: id,
            title: title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? kind : title,
            kind: kind,
            chunkIndex: 0,
            chunkCount: chunks.count,
            updatedAt: now
        )
        var index = readIndex()
        index.lastId = id
        index.books.append(entry)
        writeIndex(index)
        return entry
    }

    func delete(id: String) {
        var index = readIndex()
        if index.lastId == id { index.lastId = nil }
        index.books.removeAll { $0.id == id }
        writeIndex(index)
        try? FileManager.default.removeItem(at: root.appendingPathComponent("\(id).json"))
    }

    func updatePosition(id: String, chunkIndex: Int, now: Int64 = ShelfStore.now()) {
        var index = readIndex()
        index.books = index.books.map { entry in
            guard entry.id == id else { return entry }
            let last = max(entry.chunkCount - 1, 0)
            var copy = entry
            copy.chunkIndex = min(max(chunkIndex, 0), last)
            copy.updatedAt = now
            return copy
        }
        index.lastId = id
        writeIndex(index)
    }

    static func now() -> Int64 { Int64(Date().timeIntervalSince1970 * 1000) }

    private func uniqueId(_ now: Int64) -> String {
        var id = String(now)
        var n = 0
        while FileManager.default.fileExists(atPath: root.appendingPathComponent("\(id).json").path) {
            n += 1
            id = "\(now)-\(n)"
        }
        return id
    }

    private struct BookFile {
        var chunks: [String]
        var titles: [String]
    }

    private func readBook(_ id: String) -> BookFile {
        let url = root.appendingPathComponent("\(id).json")
        guard let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) else {
            return BookFile(chunks: [], titles: [])
        }
        if let array = json as? [String] {
            return BookFile(chunks: array, titles: Array(repeating: "", count: array.count))
        }
        let object = json as? [String: Any] ?? [:]
        let chunks = object["chunks"] as? [String] ?? []
        let rawTitles = object["titles"] as? [String] ?? []
        let titles = (0..<chunks.count).map { index in index < rawTitles.count ? rawTitles[index] : "" }
        return BookFile(chunks: chunks, titles: titles)
    }

    private func writeBook(id: String, chunks: [String], titles: [String]) {
        let body: [String: Any] = ["chunks": chunks, "titles": titles]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        try? data.write(to: root.appendingPathComponent("\(id).json"))
    }

    private struct Index {
        var lastId: String?
        var books: [ShelfEntry]
    }

    private func readIndex() -> Index {
        let url = root.appendingPathComponent("index.json")
        guard let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return Index(lastId: nil, books: [])
        }
        let lastId = json["lastId"] as? String
        let books = (json["books"] as? [[String: Any]] ?? []).map { item in
            ShelfEntry(
                id: item["id"] as? String ?? "",
                title: item["title"] as? String ?? "",
                kind: item["kind"] as? String ?? "",
                chunkIndex: item["chunkIndex"] as? Int ?? 0,
                chunkCount: item["chunkCount"] as? Int ?? 0,
                updatedAt: (item["updatedAt"] as? NSNumber)?.int64Value ?? 0
            )
        }
        return Index(lastId: lastId?.isEmpty == true ? nil : lastId, books: books)
    }

    private func writeIndex(_ index: Index) {
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let books: [[String: Any]] = index.books.map { entry in
            [
                "id": entry.id,
                "title": entry.title,
                "kind": entry.kind,
                "chunkIndex": entry.chunkIndex,
                "chunkCount": entry.chunkCount,
                "updatedAt": entry.updatedAt,
            ]
        }
        var json: [String: Any] = ["books": books]
        json["lastId"] = index.lastId ?? NSNull()
        guard let data = try? JSONSerialization.data(withJSONObject: json) else { return }
        try? data.write(to: root.appendingPathComponent("index.json"))
    }
}
