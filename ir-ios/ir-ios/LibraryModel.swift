import AVFoundation
import Foundation

struct CardState: Equatable {
    var word: String
    var sentence: String
    var dictionary: String
    var showDictionaryGap: Bool
    var glossLabel: String
    var gloss: String
    var loading: Bool
}

@MainActor
final class LibraryModel: ObservableObject {
    @Published private(set) var entries: [ShelfEntry] = []
    @Published var path: [String] = []
    @Published private(set) var chunks: [String] = []
    @Published private(set) var titles: [String] = []
    @Published var page = 0
    @Published var selection: WordHit?
    @Published var card: CardState?
    @Published var banner: String?
    @Published private(set) var dictReady = false
    @Published var pendingDelete: ShelfEntry?

    private let shelf: ShelfStore
    private let repository: DictionaryRepository?
    private let gloss = GlossSession(engine: nil)
    private var lastTap: Date?
    let canSpeak: Bool

    init() {
        let base = LibraryModel.supportURL()
        let shelfURL = base.appendingPathComponent("shelf", isDirectory: true)
        shelf = ShelfStore(root: shelfURL)
        let dictURL = base.appendingPathComponent("ecdict.db")
        let lemmaURL = base.appendingPathComponent("lemma.en.txt")
        LibraryModel.copyBundleResource("ecdict", ext: "db", to: dictURL)
        LibraryModel.copyBundleResource("lemma.en", ext: "txt", to: lemmaURL)
        if let text = try? String(contentsOf: lemmaURL, encoding: .utf8),
           let sqlite = SqliteDict(path: dictURL.path) {
            repository = DictionaryRepository(lemma: LemmaMap.load(text), lookupExact: sqlite.lookupExact)
            dictReady = true
            self.sqlite = sqlite
        } else {
            repository = nil
            dictReady = false
            self.sqlite = nil
        }
        canSpeak = AVSpeechSynthesisVoice(language: "en-US") != nil
        entries = shelf.list()
    }

    private var sqlite: SqliteDict?
    private let speaker = AVSpeechSynthesizer()

    func importFile(name: String, mime: String?, data: Data) {
        do {
            let imported = try BookImport.chunks(name: name, mime: mime, data: data)
            let title = URL(fileURLWithPath: name).deletingPathExtension().lastPathComponent
            let entry = shelf.save(title: title, kind: imported.kind, chunks: imported.chunks)
            entries = shelf.list()
            show(entry.id)
        } catch let error as ImportFailure {
            banner = error.description
        } catch {
            banner = BookImport.failed
        }
    }

    func openSample() {
        guard let url = Bundle.main.url(forResource: "sample", withExtension: "txt"),
              let data = try? Data(contentsOf: url) else {
            banner = BookImport.failed
            return
        }
        importFile(name: "sample.txt", mime: "text/plain", data: data)
    }

    func show(_ id: String) {
        chunks = shelf.loadChunks(id: id)
        titles = shelf.loadTitles(id: id)
        let entry = entries.first { $0.id == id }
        page = entry?.chunkIndex ?? 0
        selection = nil
        card = nil
        path = [id]
    }

    func delete(_ entry: ShelfEntry) {
        let wasOpen = path.first == entry.id
        shelf.delete(id: entry.id)
        entries = shelf.list()
        if wasOpen {
            path = []
            chunks = []
            selection = nil
            card = nil
        }
    }

    func turn(to index: Int) {
        guard !chunks.isEmpty else { return }
        let last = max(chunks.count - 1, 0)
        page = min(max(index, 0), last)
        selection = nil
        card = nil
        if let id = path.first {
            shelf.updatePosition(id: id, chunkIndex: page)
            entries = shelf.list()
        }
    }

    func tapWord(at index: Int) {
        guard chunks.indices.contains(page) else { return }
        let now = Date()
        if let lastTap, now.timeIntervalSince(lastTap) < 0.35 {
            clearSelection()
            self.lastTap = nil
            return
        }
        lastTap = now
        let text = chunks[page]
        if let selection {
            self.selection = WordSelector.span(text: text, anchor: selection.start, focus: index)
        } else {
            selection = WordSelector.at(text: text, index: index)
        }
        card = nil
    }

    func clearSelection() {
        selection = nil
        card = nil
        speaker.stopSpeaking(at: .immediate)
    }

    func dismissCard() {
        card = nil
    }

    func explainWord() async {
        guard let selection else { return }
        let base = ExplainPipeline.dictionaryCard(selected: selection.word, sentence: selection.sentence, dict: repository)
        card = CardState(
            word: base.word,
            sentence: base.example,
            dictionary: base.translation,
            showDictionaryGap: !dictReady,
            glossLabel: "词",
            gloss: "",
            loading: true
        )
        let line = await gloss.word(selected: selection.word, sentence: selection.sentence)
        guard var card, card.word == base.word, card.glossLabel == "词" else { return }
        card.gloss = line
        card.loading = false
        self.card = card
    }

    func explainSentence() async {
        guard let selection else { return }
        let base = ExplainPipeline.dictionaryCard(selected: selection.word, sentence: selection.sentence, dict: repository)
        card = CardState(
            word: base.word,
            sentence: base.example,
            dictionary: base.translation,
            showDictionaryGap: !dictReady,
            glossLabel: "句",
            gloss: "",
            loading: true
        )
        let line = await gloss.sentence(selection.sentence)
        guard var card, card.word == base.word, card.glossLabel == "句" else { return }
        card.gloss = line
        card.loading = false
        self.card = card
    }

    func speak() {
        guard let selection, canSpeak else { return }
        speaker.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: selection.word)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        speaker.speak(utterance)
    }

    func chapterTitle(at index: Int) -> String {
        let stored = index < titles.count ? titles[index] : ""
        return ChapterLabels.label(title: stored, index: index)
    }

    private static func supportURL() -> URL {
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("ir-ios", isDirectory: true)
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }

    private static func copyBundleResource(_ name: String, ext: String, to dest: URL) {
        if FileManager.default.fileExists(atPath: dest.path) { return }
        guard let src = Bundle.main.url(forResource: name, withExtension: ext) else { return }
        try? FileManager.default.copyItem(at: src, to: dest)
    }
}
