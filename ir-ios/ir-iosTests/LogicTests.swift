import XCTest
@testable import IRApp

final class LogicTests: XCTestCase {
    func testFileKindUsesSuffixThenMime() {
        XCTAssertEqual(FileKind.detect(name: "notes.TXT", mime: nil), "txt")
        XCTAssertEqual(FileKind.detect(name: "book.epub", mime: nil), "epub")
        XCTAssertEqual(FileKind.detect(name: "file.doc", mime: "application/pdf"), nil)
        XCTAssertEqual(FileKind.detect(name: "noext", mime: "application/pdf; charset=binary"), "pdf")
        XCTAssertNil(FileKind.detect(name: "noext", mime: "application/zip"))
    }

    func testChunkerPacksShortParagraphs() {
        XCTAssertEqual(Chunker.chunk("   \n\n  "), [])
        XCTAssertEqual(
            Chunker.chunk("Hello world.\n\nSecond line.", maxWords: 400),
            ["Hello world.\n\nSecond line."]
        )
    }

    func testSenseParserSkipsHiddenLines() {
        let senses = SenseParser.parse(translation: "n. apple\n[时态] past\n1. v. run\n(高考 1/2)", posField: nil)
        XCTAssertEqual(senses.map(\.pos), ["n", "v"])
        XCTAssertEqual(senses.map(\.translation), ["apple", "run"])
    }

    func testLemmaStem() {
        let map = LemmaMap.load("be/verb -> is, are\n; comment\n")
        XCTAssertEqual(map.stem("ARE"), "be")
        XCTAssertEqual(map.stem("be"), "be")
        XCTAssertEqual(map.stem("missing"), "missing")
    }

    func testWordAndGlossText() {
        let hit = WordSelector.at(text: "Cats sit.", index: 0)
        XCTAssertEqual(hit?.word, "Cats")
        XCTAssertEqual(hit?.sentence, "Cats sit.")
        XCTAssertEqual(GlossText.chinese("<think>secret</think>苹果"), "苹果")
        XCTAssertEqual(GlossText.chinese("hello"), "")
        XCTAssertEqual(ChapterLabels.label(title: " ", index: 0), "第 1 段")
        XCTAssertEqual(ChapterLabels.label(title: "Intro", index: 2), "Intro")
        XCTAssertTrue(GlossPrompt.isPhrase("open window"))
        XCTAssertFalse(GlossPrompt.isPhrase("cat"))
    }

    func testDictionaryCard() {
        let repo = DictionaryRepository(lemma: LemmaMap.load("cat/n -> cats")) { word in
            word == "cat" ? DictRow(word: "cat", pos: "n", translation: "n. 猫") : nil
        }
        let hit = ExplainPipeline.dictionaryCard(selected: "cats", sentence: "Cats sit.", dict: repo)
        XCTAssertEqual(hit.status, .ok)
        XCTAssertEqual(hit.word, "cat")
        XCTAssertEqual(hit.translation, "n 猫")
        let miss = ExplainPipeline.dictionaryCard(selected: "zzz", sentence: "Zzz.", dict: repo)
        XCTAssertEqual(miss.status, .notInDict)
        XCTAssertEqual(miss.word, "zzz")
        XCTAssertEqual(miss.translation, "")
    }

    func testQwenStub() async {
        let session = GlossSession(engine: nil)
        let line = await session.word(selected: "cat", sentence: "The cat sat.")
        XCTAssertEqual(line, QwenCopy.notConnected)
    }

    func testDeflateRoundTrip() {
        let text = Data("Hello EPUB".utf8)
        let compressed = RawInflate.deflate(text)
        let back = compressed.flatMap(RawInflate.inflate)
        XCTAssertEqual(back, text)
    }

    func testStoredEpubParagraph() throws {
        let container = Data(
            """
            <container><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>
            """.utf8
        )
        let opf = Data(
            """
            <package><manifest><item id="c" href="chap.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c"/></spine></package>
            """.utf8
        )
        let chapter = Data("<html><body><p>Hello world.</p></body></html>".utf8)
        let zip = StoredZip.make([
            ("META-INF/container.xml", container),
            ("OEBPS/content.opf", opf),
            ("OEBPS/chap.xhtml", chapter),
        ])
        let text = try EpubText.extract(zip)
        XCTAssertEqual(text, "Hello world.")
        let imported = try BookImport.chunks(name: "demo.epub", mime: nil, data: zip)
        XCTAssertEqual(imported.kind, "epub")
        XCTAssertEqual(imported.chunks, ["Hello world."])
    }

    func testShelfSaveAndDelete() {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = ShelfStore(root: root)
        let entry = store.save(title: "Demo", kind: "txt", chunks: ["One", "Two"], now: 10)
        XCTAssertEqual(store.list().map(\.title), ["Demo"])
        XCTAssertEqual(store.loadChunks(id: entry.id), ["One", "Two"])
        store.updatePosition(id: entry.id, chunkIndex: 5, now: 11)
        XCTAssertEqual(store.list().first?.chunkIndex, 1)
        store.delete(id: entry.id)
        XCTAssertTrue(store.list().isEmpty)
        try? FileManager.default.removeItem(at: root)
    }
}

private enum StoredZip {
    static func make(_ entries: [(String, Data)]) -> Data {
        var locals = Data()
        var central = Data()
        var offsets: [Int] = []
        for (name, payload) in entries {
            offsets.append(locals.count)
            let nameBytes = Data(name.utf8)
            var local = Data()
            appendLE32(&local, 0x04034b50)
            appendLE16(&local, 20)
            appendLE16(&local, 0)
            appendLE16(&local, 0)
            appendLE16(&local, 0)
            appendLE16(&local, 0)
            appendLE32(&local, 0)
            appendLE32(&local, UInt32(payload.count))
            appendLE32(&local, UInt32(payload.count))
            appendLE16(&local, UInt16(nameBytes.count))
            appendLE16(&local, 0)
            local.append(nameBytes)
            local.append(payload)
            locals.append(local)
        }
        for (index, entry) in entries.enumerated() {
            let nameBytes = Data(entry.0.utf8)
            var item = Data()
            appendLE32(&item, 0x02014b50)
            appendLE16(&item, 20)
            appendLE16(&item, 20)
            appendLE16(&item, 0)
            appendLE16(&item, 0)
            appendLE16(&item, 0)
            appendLE16(&item, 0)
            appendLE32(&item, 0)
            appendLE32(&item, UInt32(entry.1.count))
            appendLE32(&item, UInt32(entry.1.count))
            appendLE16(&item, UInt16(nameBytes.count))
            appendLE16(&item, 0)
            appendLE16(&item, 0)
            appendLE16(&item, 0)
            appendLE16(&item, 0)
            appendLE32(&item, 0)
            appendLE32(&item, UInt32(offsets[index]))
            item.append(nameBytes)
            central.append(item)
        }
        var eocd = Data()
        appendLE32(&eocd, 0x06054b50)
        appendLE16(&eocd, 0)
        appendLE16(&eocd, 0)
        appendLE16(&eocd, UInt16(entries.count))
        appendLE16(&eocd, UInt16(entries.count))
        appendLE32(&eocd, UInt32(central.count))
        appendLE32(&eocd, UInt32(locals.count))
        appendLE16(&eocd, 0)
        return locals + central + eocd
    }

    private static func appendLE16(_ data: inout Data, _ value: UInt16) {
        data.append(UInt8(value & 0xff))
        data.append(UInt8((value >> 8) & 0xff))
    }

    private static func appendLE32(_ data: inout Data, _ value: UInt32) {
        data.append(UInt8(value & 0xff))
        data.append(UInt8((value >> 8) & 0xff))
        data.append(UInt8((value >> 16) & 0xff))
        data.append(UInt8((value >> 24) & 0xff))
    }
}
