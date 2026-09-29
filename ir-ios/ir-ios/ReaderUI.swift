import SwiftUI
import UniformTypeIdentifiers

struct FlowLayout: Layout {
    var spacing: CGFloat = 4
    var lineSpacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 320
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width {
                x = 0
                y += rowHeight + lineSpacing
                rowHeight = 0
            }
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return CGSize(width: width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + lineSpacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(width: size.width, height: size.height))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
    }
}

struct ReadingToken: Identifiable {
    let id: Int
    let text: String
    let start: Int
    let isWord: Bool
}

enum ReadingTokens {
    static func paragraphs(in text: String) -> [[ReadingToken]] {
        var paragraphs: [[ReadingToken]] = [[]]
        var tokenID = 0
        var index = 0
        var word = ""
        var wordStart = 0
        let chars = Array(text)

        func flushWord() {
            guard !word.isEmpty else { return }
            paragraphs[paragraphs.count - 1].append(ReadingToken(id: tokenID, text: word, start: wordStart, isWord: true))
            tokenID += 1
            word = ""
        }

        while index < chars.count {
            let ch = chars[index]
            if ch == "\n" {
                flushWord()
                if index + 1 < chars.count, chars[index + 1] == "\n" {
                    paragraphs.append([])
                    while index < chars.count, chars[index] == "\n" { index += 1 }
                    continue
                }
                index += 1
                continue
            }
            if ch.isLetter {
                if word.isEmpty { wordStart = index }
                word.append(ch)
            } else if ch.isWhitespace {
                if !word.isEmpty {
                    paragraphs[paragraphs.count - 1].append(ReadingToken(id: tokenID, text: word + " ", start: wordStart, isWord: true))
                    tokenID += 1
                    word = ""
                }
            } else {
                flushWord()
                paragraphs[paragraphs.count - 1].append(ReadingToken(id: tokenID, text: String(ch), start: index, isWord: false))
                tokenID += 1
            }
            index += 1
        }
        flushWord()
        return paragraphs.filter { !$0.isEmpty }
    }
}

struct RootView: View {
    @StateObject private var model = LibraryModel()
    @State private var showImporter = false
    @State private var showSettings = false

    var body: some View {
        NavigationStack(path: $model.path) {
            shelf
                .navigationTitle("书架")
                .navigationDestination(for: String.self) { _ in
                    ReaderView(model: model)
                }
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("设置") { showSettings = true }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("导入") { showImporter = true }
                    }
                }
        }
        .fileImporter(
            isPresented: $showImporter,
            allowedContentTypes: importTypes,
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                guard let url = urls.first else { return }
                let access = url.startAccessingSecurityScopedResource()
                defer { if access { url.stopAccessingSecurityScopedResource() } }
                guard let data = try? Data(contentsOf: url) else {
                    model.banner = BookImport.failed
                    return
                }
                model.importFile(name: url.lastPathComponent, mime: nil, data: data)
            case .failure(let error):
                let ns = error as NSError
                if ns.domain == NSCocoaErrorDomain && ns.code == NSUserCancelledError { return }
                model.banner = BookImport.failed
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView(dictReady: model.dictReady)
        }
        .alert("导入", isPresented: Binding(
            get: { model.banner != nil },
            set: { if !$0 { model.banner = nil } }
        )) {
            Button("好", role: .cancel) { model.banner = nil }
        } message: {
            Text(model.banner ?? "")
        }
        .confirmationDialog("删除这本书？", isPresented: Binding(
            get: { model.pendingDelete != nil },
            set: { if !$0 { model.pendingDelete = nil } }
        ), titleVisibility: .visible) {
            Button("删除", role: .destructive) {
                if let entry = model.pendingDelete { model.delete(entry) }
                model.pendingDelete = nil
            }
            Button("取消", role: .cancel) { model.pendingDelete = nil }
        }
    }

    private var shelf: some View {
        Group {
            if model.entries.isEmpty {
                VStack(spacing: 16) {
                    Text("书架是空的")
                        .font(.title3)
                    Button("打开范文") { model.openSample() }
                    Button("导入 TXT / EPUB / PDF") { showImporter = true }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(model.entries) { entry in
                    Button {
                        model.show(entry.id)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(entry.title).font(.headline).foregroundStyle(.primary)
                            Text("\(entry.kind.uppercased()) · \(entry.chunkIndex + 1)/\(max(entry.chunkCount, 1))")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .swipeActions {
                        Button("删除", role: .destructive) { model.pendingDelete = entry }
                    }
                }
            }
        }
    }

    private var importTypes: [UTType] {
        var types: [UTType] = [.plainText, .pdf, .utf8PlainText]
        if let epub = UTType(filenameExtension: "epub") { types.append(epub) }
        return types
    }
}

struct SettingsView: View {
    let dictReady: Bool
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("词典") {
                    Text(dictReady ? "ECDICT 已放进这台设备。" : "还没有词典。把 ecdict.db 和 lemma.en.txt 放进 Xcode 工程里的 ir-ios 文件夹，重新 Run。")
                }
                Section("Qwen") {
                    Text("「词」和「句」的接口已经留好。iOS 上的模型运行时还没接，点了会说明这一点。词典这一栏不依赖模型。")
                }
            }
            .navigationTitle("设置")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }
}

struct ReaderView: View {
    @ObservedObject var model: LibraryModel
    @State private var showChapters = false

    var body: some View {
        VStack(spacing: 0) {
            if model.chunks.isEmpty {
                Text(BookImport.failed).padding()
            } else {
                TabView(selection: Binding(
                    get: { model.page },
                    set: { model.turn(to: $0) }
                )) {
                    ForEach(model.chunks.indices, id: \.self) { index in
                        page(model.chunks[index], active: index == model.page)
                            .tag(index)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
            }
            if model.selection != nil {
                actionBar
            }
        }
        .navigationTitle(model.chunks.isEmpty ? "阅读" : "\(model.page + 1) / \(model.chunks.count)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("章节") { showChapters = true }
                    .disabled(model.chunks.isEmpty)
            }
        }
        .sheet(isPresented: $showChapters) {
            NavigationStack {
                List(model.chunks.indices, id: \.self) { index in
                    Button(model.chapterTitle(at: index)) {
                        model.turn(to: index)
                        showChapters = false
                    }
                }
                .navigationTitle("章节")
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("完成") { showChapters = false }
                    }
                }
            }
        }
        .overlay(alignment: .bottom) {
            if let card = model.card {
                ExplainCardView(card: card) { model.dismissCard() }
                    .padding()
            }
        }
    }

    private func page(_ text: String, active: Bool) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                ForEach(Array(ReadingTokens.paragraphs(in: text).enumerated()), id: \.offset) { _, tokens in
                    FlowLayout(spacing: 0, lineSpacing: 6) {
                        ForEach(tokens) { token in
                            if token.isWord {
                                Text(token.text)
                                    .font(.title3)
                                    .padding(.horizontal, 1)
                                    .background(highlight(token))
                                    .onTapGesture { if active { model.tapWord(at: token.start) } }
                            } else {
                                Text(token.text)
                                    .font(.title3)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(20)
            .frame(maxWidth: 680)
            .frame(maxWidth: .infinity)
        }
        .onTapGesture(count: 2) { model.clearSelection() }
    }

    private func highlight(_ token: ReadingToken) -> Color {
        guard let selection = model.selection else { return .clear }
        let end = token.start + token.text.count
        if token.start < selection.end, end > selection.start { return Color.yellow.opacity(0.45) }
        return .clear
    }

    private var actionBar: some View {
        HStack(spacing: 12) {
            Button("词") { Task { await model.explainWord() } }
            Button("句") { Task { await model.explainSentence() } }
            if model.canSpeak {
                Button("读") { model.speak() }
            }
            Spacer()
            Button("清除") { model.clearSelection() }
        }
        .font(.headline)
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .background(.bar)
    }
}

struct ExplainCardView: View {
    let card: CardState
    var close: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(card.word).font(.title3.bold())
            if card.showDictionaryGap {
                Text("词典还没放进这台设备。").foregroundStyle(.secondary)
            } else if !card.dictionary.isEmpty {
                Text(card.dictionary)
            }
            if card.loading {
                ProgressView()
            } else if !card.gloss.isEmpty {
                Text("\(card.glossLabel)：\(card.gloss)")
            }
            Button("关闭", action: close)
                .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(radius: 8)
    }
}

@main
struct YApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
