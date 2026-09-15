"""Optional Langfuse tracing. Fail-open: never raise into LLM callers."""
from __future__ import annotations

import atexit
import logging
import os
import sys
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger(__name__)

_warned = False
_dotenv_loaded = False
_applied_base_url: str | None = None

DOTENV_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".env"))


class _NoOpGeneration:
    def update(self, **kwargs: Any) -> None:
        return None

    def end(self) -> None:
        return None


def reset_for_tests() -> None:
    """Clear process-level caches so pytest env changes take effect."""
    global _warned, _dotenv_loaded, _applied_base_url
    _warned = False
    _dotenv_loaded = False
    _applied_base_url = None


def _load_repo_dotenv() -> None:
    """Load repo-root .env into os.environ without overriding existing values."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    path = DOTENV_PATH
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if not key:
                    continue
                existing = os.environ.get(key)
                if existing is None or existing == "":
                    os.environ[key] = value
    except Exception as exc:
        _warn_once(exc)


def is_enabled() -> bool:
    _load_repo_dotenv()
    return bool(
        (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
        and (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
    )


def _warn_once(exc: BaseException) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    log.warning("Langfuse tracing disabled after error: %s", exc)


def _langfuse_host() -> str:
    return (
        (os.environ.get("LANGFUSE_BASE_URL") or "").strip()
        or (os.environ.get("LANGFUSE_HOST") or "").strip()
        or "http://localhost:3000"
    )


def _apply_host_default() -> None:
    """Ensure self-hosted default, not Langfuse Cloud, when keys are set."""
    global _applied_base_url
    if not is_enabled():
        return
    if (os.environ.get("LANGFUSE_BASE_URL") or "").strip():
        return
    host = _langfuse_host()
    os.environ["LANGFUSE_BASE_URL"] = host
    _applied_base_url = host


@contextmanager
def _null_ctx() -> Iterator[None]:
    yield None


def _safe_exit(cm: Any) -> None:
    try:
        cm.__exit__(*sys.exc_info())
    except Exception as exc:
        _warn_once(exc)


@contextmanager
def start_generation(
    *,
    name: str,
    model: str,
    input: Any = None,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> Iterator[Any]:
    """Yield a Langfuse generation or a no-op. Always safe to use as `with`."""
    if not is_enabled():
        yield _NoOpGeneration()
        return
    _apply_host_default()
    stack: list[Any] = []
    gen: Any = None
    try:
        from langfuse import get_client, propagate_attributes

        client = get_client()
        attrs = {}
        if session_id:
            attrs["session_id"] = session_id
        pa = propagate_attributes(**attrs) if attrs else _null_ctx()
        pa.__enter__()
        stack.append(pa)
        obs = client.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input,
            metadata=metadata or {},
        )
        gen = obs.__enter__()
        stack.append(obs)
    except Exception as exc:
        _warn_once(exc)
        while stack:
            _safe_exit(stack.pop())
        yield _NoOpGeneration()
        return
    try:
        yield gen
    finally:
        while stack:
            _safe_exit(stack.pop())


def openai_client_class():
    """Return OpenAI class: Langfuse drop-in when enabled, else stock openai."""
    _apply_host_default()
    if is_enabled():
        try:
            from langfuse.openai import OpenAI
            return OpenAI
        except Exception as exc:
            _warn_once(exc)
    from openai import OpenAI
    return OpenAI


def make_openai_client(*, api_key: str, base_url: str):
    """Build an OpenAI-compatible client. Fail-open to stock SDK if Langfuse wrapper breaks."""
    try:
        cls = openai_client_class()
        return cls(api_key=api_key, base_url=base_url)
    except Exception as exc:
        _warn_once(exc)
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url)


def flush() -> None:
    if not is_enabled():
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception as exc:
        _warn_once(exc)


atexit.register(flush)
