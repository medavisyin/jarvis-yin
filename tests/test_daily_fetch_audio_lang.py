"""Daily Fetch audio language must follow live Global Settings."""

from __future__ import annotations

import ast
import logging
import os
import tempfile
import types

_DAILY_FETCH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "scripts", "rag", "routes", "daily_fetch.py")
)

_WANT_FNS = {
    "_resolve_audio_lang",
    "_audio_already_done",
    "_write_audio_lang_sidecar",
    "_resolve_agent_from",
    "_pick_global_settings",
    "_should_skip_audio_step",
    "_mp3_was_replaced",
}
_WANT_ASSIGN = {
    "_AUDIO_STEP_LANG_KEYS",
    "_AUDIO_MP3_NAMES",
    "_AGENT_MODULE_CANDIDATES",
}


def _load_helpers():
    src = open(_DAILY_FETCH, encoding="utf-8").read()
    tree = ast.parse(src)
    body = []
    found_fn = set()
    found_assign = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANT_FNS:
            body.append(node)
            found_fn.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in _WANT_ASSIGN:
                    body.append(node)
                    found_assign.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in _WANT_ASSIGN:
                body.append(node)
                found_assign.add(node.target.id)
    missing = (_WANT_FNS - found_fn) | (_WANT_ASSIGN - found_assign)
    assert not missing, f"missing from daily_fetch.py: {sorted(missing)}"
    mod = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(mod)
    ns: dict = {"os": os, "_log": logging.getLogger("test_daily_fetch_audio")}
    exec(compile(mod, _DAILY_FETCH, "exec"), ns)
    return ns


def test_resolve_audio_lang_uses_global_without_overrides():
    h = _load_helpers()
    gs = {"audio_lang_ai": "zh", "audio_lang_finance": "en"}
    assert h["_resolve_audio_lang"]("ai_audio", gs, None) == "zh"
    assert h["_resolve_audio_lang"]("finance_audio", gs, {}) == "en"


def test_resolve_audio_lang_override_only_when_explicit():
    h = _load_helpers()
    gs = {"audio_lang_ai": "zh"}
    assert h["_resolve_audio_lang"]("ai_audio", gs, {"ai_audio": "en"}) == "en"


def test_audio_already_done_false_when_mp3_missing():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        assert h["_audio_already_done"](td, "ai_audio", "zh") is False


def test_audio_already_done_false_for_legacy_mp3_without_sidecar():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "ai-briefing.mp3"), "wb").close()
        assert h["_audio_already_done"](td, "ai_audio", "zh") is False


def test_audio_already_done_false_when_sidecar_lang_differs():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "ai-briefing.mp3"), "wb").close()
        h["_write_audio_lang_sidecar"](td, "ai_audio", "en")
        assert h["_audio_already_done"](td, "ai_audio", "zh") is False


def test_audio_already_done_true_when_sidecar_matches_global():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "finance-markets.mp3"), "wb").close()
        h["_write_audio_lang_sidecar"](td, "finance_audio", "zh")
        assert h["_audio_already_done"](td, "finance_audio", "zh") is True


def test_resolve_agent_prefers_main_over_stale_agent_import():
    h = _load_helpers()
    main = types.SimpleNamespace(
        _load_session_file=lambda *a, **k: None,
        _GLOBAL_SETTINGS={"audio_lang_ai": "zh"},
    )
    stale = types.SimpleNamespace(
        _load_session_file=lambda *a, **k: None,
        _GLOBAL_SETTINGS={"audio_lang_ai": "en"},
    )
    picked = h["_resolve_agent_from"]({"agent": stale, "__main__": main})
    assert picked is main
    gs = h["_pick_global_settings"]({"agent": stale, "__main__": main}, {"audio_lang_ai": "en"})
    assert gs["audio_lang_ai"] == "zh"


def test_agent_module_candidates_put_main_first():
    h = _load_helpers()
    assert h["_AGENT_MODULE_CANDIDATES"][0] == "__main__"


def test_skip_audio_false_when_only_steps_requested():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "ai-briefing.mp3"), "wb").close()
        h["_write_audio_lang_sidecar"](td, "ai_audio", "zh")
        assert h["_should_skip_audio_step"](["ai_audio"], td, "ai_audio", "zh") is False


def test_skip_audio_true_on_full_run_when_sidecar_matches():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "ai-briefing.mp3"), "wb").close()
        h["_write_audio_lang_sidecar"](td, "ai_audio", "zh")
        assert h["_should_skip_audio_step"](None, td, "ai_audio", "zh") is True
        assert h["_should_skip_audio_step"]([], td, "ai_audio", "zh") is True


def test_skip_audio_false_on_full_run_when_lang_mismatches():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "ai-briefing.mp3"), "wb").close()
        h["_write_audio_lang_sidecar"](td, "ai_audio", "en")
        assert h["_should_skip_audio_step"](None, td, "ai_audio", "zh") is False


def test_mp3_was_replaced_false_when_missing_or_empty():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        missing = os.path.join(td, "ai-briefing.mp3")
        assert h["_mp3_was_replaced"](missing, None) is False
        open(missing, "wb").close()
        assert h["_mp3_was_replaced"](missing, None) is False


def test_mp3_was_replaced_true_for_new_nonempty_file():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ai-briefing.mp3")
        with open(path, "wb") as f:
            f.write(b"id3")
        assert h["_mp3_was_replaced"](path, None) is True


def test_mp3_was_replaced_false_when_mtime_unchanged():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ai-briefing.mp3")
        with open(path, "wb") as f:
            f.write(b"id3")
        mtime = os.path.getmtime(path)
        assert h["_mp3_was_replaced"](path, mtime) is False


def test_mp3_was_replaced_true_when_existing_file_rewritten():
    h = _load_helpers()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ai-briefing.mp3")
        with open(path, "wb") as f:
            f.write(b"old")
        older = os.path.getmtime(path) - 10
        os.utime(path, (older, older))
        before = os.path.getmtime(path)
        with open(path, "wb") as f:
            f.write(b"new-audio")
        newer = before + 10
        os.utime(path, (newer, newer))
        assert h["_mp3_was_replaced"](path, before) is True


def test_write_audio_lang_sidecar_does_not_raise_on_io_error():
    h = _load_helpers()
    h["_write_audio_lang_sidecar"](
        os.path.join("Z:\\no-such-daily-fetch-dir", "missing"),
        "ai_audio",
        "zh",
    )


def test_run_todays_fetch_completion_player_is_cache_busted():
    html_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "rag", "templates", "index.html")
    )
    html = open(html_path, encoding="utf-8").read()
    start = html.find("function runDailyFetchFromModal")
    assert start > 0
    chunk = html[start:start + 8000]
    assert "ai-briefing.mp3" in chunk
    assert "_cacheBust" in chunk or "?t=" in chunk
