"""TDD: intensive-reading RAG index must work while stock config occupies 'config'."""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intensive_reading.ingest import index_chunks_to_rag  # noqa: E402


def _install_stock_config():
    stock_cfg = types.ModuleType("stock_config")
    stock_cfg.REPORTS_ROOT = "C:/reports/stock"
    # Intentionally no SNAPSHOT_PATH — this is the production failure mode.
    return stock_cfg


def _install_fake_rag_stack():
    fake_re = types.ModuleType("rag_engine")
    fake_re.COLLECTION = "ai_briefings"
    fake_model = MagicMock()
    fake_model.encode.return_value = [[0.1, 0.2, 0.3]]
    fake_client = MagicMock()
    fake_re.get_embed_model = lambda: fake_model
    fake_re.get_qdrant = lambda: fake_client
    fake_re._qdrant_points = []

    fake_models = types.ModuleType("qdrant_client.models")

    class PointStruct:
        def __init__(self, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    fake_models.PointStruct = PointStruct
    fake_qc = types.ModuleType("qdrant_client")
    fake_qc.models = fake_models

    return fake_re, fake_qc, fake_models


def test_index_chunks_to_rag_when_stock_config_occupies_sys_modules():
    """Reproduce upload-time race: stock @_with_stock_imports swapped config."""
    prev_config = sys.modules.get("config")
    prev_re = sys.modules.get("rag_engine")
    prev_qc = sys.modules.get("qdrant_client")
    prev_models = sys.modules.get("qdrant_client.models")

    stock_cfg = _install_stock_config()
    fake_re, fake_qc, fake_models = _install_fake_rag_stack()
    sys.modules["config"] = stock_cfg
    sys.modules["rag_engine"] = fake_re
    sys.modules["qdrant_client"] = fake_qc
    sys.modules["qdrant_client.models"] = fake_models

    try:
        with patch("intensive_reading.ingest._merge_snapshot"):
            count, err = index_chunks_to_rag(
                "newyorker20260810-8355ce99",
                "new_yorker.2026.08.10",
                "magazine",
                [{"chunk_index": 0, "text": "A short passage.", "title": "Goings On"}],
            )
        assert "SNAPSHOT_PATH" not in (err or "")
        assert err == ""
        assert count == 1
        assert sys.modules["config"] is stock_cfg
    finally:
        if prev_config is not None:
            sys.modules["config"] = prev_config
        elif "config" in sys.modules:
            del sys.modules["config"]
        for name, prev in (
            ("rag_engine", prev_re),
            ("qdrant_client", prev_qc),
            ("qdrant_client.models", prev_models),
        ):
            if prev is not None:
                sys.modules[name] = prev
            elif name in sys.modules:
                del sys.modules[name]
