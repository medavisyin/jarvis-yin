"""Resolve Jarvis Flask bind host/port (LAN opt-in)."""

from __future__ import annotations

import argparse
import os
from typing import Mapping

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18889


def resolve_listen_config(
    argv: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, int]:
    """Return (host, port). Default host is localhost; LAN via JARVIS_HOST or --host."""
    env = os.environ if environ is None else environ
    args_list = list(argv) if argv is not None else []

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("port", nargs="?", type=int, default=None)
    parser.add_argument("--host", default=None)
    parsed, _unknown = parser.parse_known_args(args_list)

    host = parsed.host or env.get("JARVIS_HOST") or DEFAULT_HOST
    port = DEFAULT_PORT if parsed.port is None else parsed.port
    return host, port
