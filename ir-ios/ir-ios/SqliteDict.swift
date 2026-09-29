import Foundation
import SQLite3

final class SqliteDict {
    private var db: OpaquePointer?
    private let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    init?(path: String) {
        if sqlite3_open_v2(path, &db, SQLITE_OPEN_READONLY, nil) != SQLITE_OK {
            sqlite3_close(db)
            db = nil
            return nil
        }
    }

    deinit { sqlite3_close(db) }

    func lookupExact(_ word: String) -> DictRow? {
        let sql = "SELECT word, pos, translation FROM stardict WHERE word = ? COLLATE NOCASE LIMIT 1"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, word, -1, transient)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return nil }
        let found = columnText(stmt, 0) ?? word
        let pos = sqlite3_column_type(stmt, 1) == SQLITE_NULL ? nil : columnText(stmt, 1)
        let translation = columnText(stmt, 2) ?? ""
        return DictRow(word: found, pos: pos, translation: translation)
    }

    private func columnText(_ stmt: OpaquePointer?, _ index: Int32) -> String? {
        guard let raw = sqlite3_column_text(stmt, index) else { return nil }
        return String(cString: raw)
    }
}
