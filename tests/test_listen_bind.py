"""Unit tests for Jarvis listen host/port resolution."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from listen_bind import resolve_listen_config  # noqa: E402


def test_defaults_to_localhost_18889():
    host, port = resolve_listen_config(argv=[], environ={})
    assert host == "127.0.0.1"
    assert port == 18889


def test_env_jarvis_host_overrides_default():
    host, port = resolve_listen_config(argv=[], environ={"JARVIS_HOST": "0.0.0.0"})
    assert host == "0.0.0.0"
    assert port == 18889


def test_cli_host_overrides_env():
    host, port = resolve_listen_config(
        argv=["--host", "0.0.0.0"],
        environ={"JARVIS_HOST": "127.0.0.1"},
    )
    assert host == "0.0.0.0"
    assert port == 18889


def test_positional_port_still_works():
    host, port = resolve_listen_config(argv=["19000"], environ={})
    assert host == "127.0.0.1"
    assert port == 19000


def test_host_and_port_together():
    host, port = resolve_listen_config(
        argv=["--host", "0.0.0.0", "19001"],
        environ={},
    )
    assert host == "0.0.0.0"
    assert port == 19001
