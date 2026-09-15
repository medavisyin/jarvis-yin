"""Migration of legacy world/china audio lang → finance."""

from __future__ import annotations

import ast
import os


def _load_migrate_fn():
    """Parse agent.py and exec only _migrate_audio_lang_finance (avoid Flask import)."""
    agent_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "rag", "agent.py")
    )
    src = open(agent_path, encoding="utf-8").read()
    tree = ast.parse(src)
    target = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_migrate_audio_lang_finance":
            target = node
            break
    assert target is not None, "_migrate_audio_lang_finance missing from agent.py"
    mod = ast.Module(body=[target], type_ignores=[])
    ast.fix_missing_locations(mod)
    ns: dict = {}
    exec(compile(mod, agent_path, "exec"), ns)
    return ns["_migrate_audio_lang_finance"]


_migrate = _load_migrate_fn()


def test_migrates_world_lang_when_finance_never_saved():
    settings = {"audio_lang_ai": "zh", "audio_lang_finance": "zh"}
    saved = {"audio_lang_ai": "zh", "audio_lang_world": "en"}
    out = _migrate(settings, saved)
    assert out["audio_lang_finance"] == "en"


def test_keeps_explicitly_saved_finance_zh():
    settings = {"audio_lang_ai": "zh", "audio_lang_finance": "zh"}
    saved = {"audio_lang_ai": "zh", "audio_lang_finance": "zh", "audio_lang_world": "en"}
    out = _migrate(settings, saved)
    assert out["audio_lang_finance"] == "zh"


def test_defaults_to_zh_without_legacy_keys():
    settings = {"audio_lang_finance": "zh"}
    saved = {}
    out = _migrate(settings, saved)
    assert out["audio_lang_finance"] == "zh"
