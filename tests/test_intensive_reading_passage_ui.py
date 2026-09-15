"""Contract: intensive-reading Passage / Chapters UI in index.html."""
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"


def test_articles_ui_shown_for_novels():
    text = HTML.read_text(encoding="utf-8")
    fn = text[text.find("function irSyncArticlesUi"):text.find("function irRenderArticlesPop")]
    assert "novel" in fn
    assert "Chapters" in text[text.find("function irSyncArticlesUi"):text.find("async function irRefreshBooks")]
    assert "Pages" in fn  # hide dropdown when titles are Pages N-M


def test_open_book_loads_toc_for_novels():
    text = HTML.read_text(encoding="utf-8")
    fn = text[text.find("async function irOpenBook"):text.find("function irRenderPassage")]
    assert "Array.isArray(meta.toc)" in fn
    assert "_irState.toc = (_irState.bookType === 'magazine' && Array.isArray(meta.toc))" not in fn


def test_toggle_articles_allows_novel():
    text = HTML.read_text(encoding="utf-8")
    assert "if (_irState.bookType !== 'magazine') return;" not in text
    fn = text[text.find("function irToggleArticlesPop"):text.find("async function irRefreshBooks")]
    assert "novel" in fn


def test_chapter_active_spans_subchunks():
    text = HTML.read_text(encoding="utf-8")
    fn = text[text.find("function irRenderArticlesPop"):text.find("function irToggleArticlesPop")]
    assert "nextStart" in fn
    assert "chunkIndex >= entry.chunk_index" in fn.replace(" ", "") or (
        "_irState.chunkIndex >= entry.chunk_index" in fn
    )


def test_passage_css_is_reading_theme():
    text = HTML.read_text(encoding="utf-8")
    css = text[text.find("#irPassage{"):text.find("#irExplainBtn")]
    assert "Literata" in css
    assert "Georgia" in css  # fallback
    assert "@font-face" in text
    assert "/static/fonts/literata-latin-400-normal.woff2" in text
    assert "/static/fonts/literata-latin-400-italic.woff2" in text
    assert "/static/fonts/literata-latin-600-normal.woff2" in text
    assert "38em" in css.replace(" ", "")
    assert "text-align:left" in css.replace(" ", "") or "text-align: left" in css
    assert "#d6d2c8" in css
    assert "#16141a" in css
    assert "text-align:justify" not in css.replace(" ", "")
    assert "fonts.googleapis" not in text
    analysis = text[text.find("#irAnalysis{"):text.find("#irSpeakingPane")]
    assert "Literata" not in analysis


def test_literata_woff2_files_present():
    fonts = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "static" / "fonts"
    for name in (
        "literata-latin-400-normal.woff2",
        "literata-latin-400-italic.woff2",
        "literata-latin-600-normal.woff2",
    ):
        path = fonts / name
        assert path.is_file(), name
        assert path.stat().st_size > 1000, name
    ofl = fonts / "OFL-Literata.txt"
    assert ofl.is_file()
    assert "SIL Open Font License" in ofl.read_text(encoding="utf-8")


def test_article_title_uses_registered_literata_weight():
    text = HTML.read_text(encoding="utf-8")
    css = text[text.find("#irPassage .ir-article-title"):text.find("#irExplainBtn")]
    compact = css.replace(" ", "")
    assert "font-weight:600" in compact
    assert "font-weight:650" not in compact


def test_agent_registers_woff2_mime():
    agent = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "agent.py"
    text = agent.read_text(encoding="utf-8")
    assert "mimetypes.add_type" in text
    assert "font/woff2" in text
    assert ".woff2" in text


def test_passage_novel_vs_magazine_para_rules():
    text = HTML.read_text(encoding="utf-8")
    assert "ir-kind-novel" in text
    assert "ir-kind-magazine" in text
    fn = text[text.find("function irRenderPassage"):text.find("function irRenderPlainParas")]
    assert "ir-kind-novel" in fn and "ir-kind-magazine" in fn
    assert "ir-reading-col" in fn
    assert "articleTitle" in fn
    css = text[text.find("#irPassage{"):text.find("#irExplainBtn")]
    assert "margin:0 0 0.28em" not in css
    assert "ir-kind-magazine .ir-para{margin:0 0 0.9em;text-indent:0}" not in css
    merged = (
        "#irPassage.ir-kind-novel .ir-para,\n"
        "#irPassage.ir-kind-magazine .ir-para{margin:0 0 1em;text-indent:1.25em}"
    )
    assert merged in css
    assert "#irPassage .ir-para.ir-title{text-indent:0" in css
    assert "#irPassage .ir-para.ir-kicker{text-indent:0" in css
    assert "#irPassage .ir-article-title{margin:0 0 0.85em" in css
    assert "text-indent:0;text-align:left;font-weight:600;font-size:1.22em" in css
    analysis = text[text.find("#irAnalysis .ir-para"):text.find("#irSpeakingPane")]
    assert "text-indent:0" in analysis.replace(" ", "")


def test_analysis_header_has_level_and_output_lang_selects():
    text = HTML.read_text(encoding="utf-8")
    assert 'id="irLearnerLevel"' in text
    assert 'value="university"' in text
    assert 'value="high_school"' in text
    assert 'value="middle_school"' in text
    footer = text[text.find('id="irAnalysis"'):text.find('id="irBackBtn"')]
    assert 'id="irOutputLang"' in footer
    assert 'id="irGenerateBtn"' in footer
    assert footer.find('id="irOutputLang"') < footer.find('id="irGenerateBtn"')
    assert 'value="zh"' in footer
    assert 'value="en"' in footer
    assert 'selected>' in footer or 'selected>' in text[text.find('id="irOutputLang"'):text.find('id="irGenerateBtn"')]
    assert 'option value="zh" selected' in text
    get_lang = text[text.find("function irGetOutputLang"):text.find("function irTabCacheKey")]
    assert "irOutputLang" in get_lang
    lookup = text[text.find("function irLookupCachedTab"):text.find("async function irOnLearnerPrefsChange")]
    compact = lookup.replace(" ", "")
    assert "irGetOutputLang()!=='en'" in compact
    assert "function irLegacyKindFallback" not in text
    show = text[text.find("function irShowActiveAnalysis"):text.find("function irCaptureSpeakingOral")]
    assert "analyze (English)." not in show
    assert "irGetOutputLang" in show
    cont = text[text.find("function irUpdateContinueBtn"):text.find("async function irGenerateActiveTab")]
    assert "irOutputLangWrap" in cont
    gen = text[text.find("async function irRunAnalyzeKind"):text.find("async function irGenerateActiveTab") + 1]
    analyze = text[text.find("async function irRunAnalyzeKind"):text.find("function irBindSelectionExplain")]
    assert "output_lang: irGetOutputLang()" in analyze.replace(" ", "") or "output_lang: irGetOutputLang()" in text
    open_fn = text[text.find("function openIntensiveReadingModal"):text.find("function closeIntensiveReadingModal")]
    assert "irLoadLearnerPrefs" in open_fn
    assert "irSaveLearnerPrefs" in open_fn
    assert 'jarvis.ir.learnerLevel' in text
    assert 'jarvis.ir.outputLang' in text
    assert 'learner_level' in text
    assert "function irTabCacheKey" in text
    assert "irPersistSpeaking" in text[text.find("async function irOnLearnerPrefsChange"):text.find("function irLoadLearnerPrefs")]


def test_novel_socratic_tab_is_reflection_ui():
    text = HTML.read_text(encoding="utf-8")
    tabs = text[text.find("var _IR_NOVEL_TABS"):text.find("var _IR_MAG_TABS")]
    assert "socratic" in tabs
    assert "读后感" in tabs
    mag = text[text.find("var _IR_MAG_TABS"):text.find("var _IR_SPEAKING_TAB")]
    assert "socratic" not in mag
    assert "irReflection" in text
    assert "irReflectionComment" in text
    assert "function irCaptureReflection" in text
    assert "learner_reflection" in text
    show = text[text.find("function irShowActiveAnalysis"):text.find("function irCaptureSpeakingOral")]
    assert "socratic" in show
    empty = text[text.find("function irEmptyAnalysisSlot"):text.find("function irEmptySpeaking")]
    assert "reflection" in empty
    persist = text[text.find("async function irPersistSlot"):text.find("async function irSaveProgress")]
    assert "reflection" in persist
    run = text[text.find("async function irRunAnalyzeKind"):text.find("function openExplainThisModal")]
    assert "irReflectionComment" in run
    assert "learner_reflection" in run
    prefs = text[text.find("async function irOnLearnerPrefsChange"):text.find("function irLoadLearnerPrefs")]
    assert "irCaptureReflection" in prefs
    compact_prefs = prefs.replace(" ", "")
    assert "keepTab" in prefs
    assert "keptReflection" in prefs
    assert "!(slot.reflection" not in compact_prefs
    assert "jarvis.ir.outputLang" in prefs
    assert "learnerLevel: oldLevel" in prefs.replace(" ", "") or "learnerLevel:oldLevel" in prefs.replace(" ", "")
    assert "outputLang: oldLang" in prefs.replace(" ", "") or "outputLang:oldLang" in prefs.replace(" ", "")
    assert "skipRender" in prefs
    persist_fn = text[text.find("async function irPersistSlot"):text.find("async function irSaveProgress")]
    assert "learnerLevel" in persist_fn or "outputLang" in persist_fn or "keyOpts" in persist_fn
    load_cached = text[text.find("async function irLoadCachedAnalysis"):text.find("async function irPersistSlot")]
    assert "keepTab" in load_cached
    assert "slot.reflection" in load_cached
    fill = text[text.find("function irFillReflectionComment"):text.find("function irShowReflectionPane")]
    assert "click Continue" not in fill
    load = text[text.find("async function irLoadChunk"):text.find("async function irLoadCachedAnalysis")]
    assert "irCaptureReflection" in load
    persist_leave = load[load.find("irCaptureReflection"):load.find("irCaptureSpeakingOral")]
    assert "prevSlot" in persist_leave
    assert "speakingLoaded" in persist_leave
    assert "((prevSlot.reflection || '').trim() || prevSlot.text)" not in load
    css = text[text.find("#irSpeakingPane{"):text.find(".modal-panel{background")]
    assert "ir-reflection-notes" in css


def test_passage_has_no_overlay_spans():
    text = HTML.read_text(encoding="utf-8")
    css = text[text.find("#irPassage{"):text.find("#irExplainBtn")]
    assert ".ir-sent" not in css
    assert ".ir-vocab" not in css
    fn = text[text.find("function irRenderPassage"):text.find("function irRenderPlainParas")]
    assert "irApplyOverlayToPara" not in fn
    assert "function irOnPassageOverlayClick" not in text


def test_explain_popover_has_speak_button():
    text = HTML.read_text(encoding="utf-8")
    css = text[text.find("#irExplainPop"):text.find("#irArticlesWrap")]
    assert ".ir-explain-speak" in css
    ensure = text[text.find("function irEnsureExplainUi"):text.find("function irHideExplainBtn")]
    assert "ir-explain-speak" in ensure
    assert "speechSynthesis" in ensure
    assert ".disabled = true" in ensure.replace(" ", "") or "disabled = true" in ensure
    toggle = text[text.find("function irToggleExplainSpeech"):text.find("function irHideExplainPop")]
    assert "_irExplainSel.text" in toggle
    assert "speechSynthesis.speaking" in toggle
    assert "en-US" in toggle
    hide = text[text.find("function irHideExplainPop"):text.find("function irHideSelectionExplain")]
    assert "irStopExplainSpeech" in hide
    stop = text[text.find("function irStopExplainSpeech"):text.find("function irToggleExplainSpeech")]
    assert "speechSynthesis.cancel" in stop.replace(" ", "") or "cancel()" in stop
