"""Flask-shaped HTTP helpers on top of FastAPI for the Jarvis agent app.

Search UI stays on Flask. This module lets agent.py and routes/ keep
`Blueprint`, `request.get_json()`, `jsonify(...)`, 404 tuples, and SSE
`Response` while serving through uvicorn.
"""
from __future__ import annotations

import functools
import re
import shutil
from contextvars import ContextVar
from typing import Any, Callable, Iterable

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from starlette.concurrency import iterate_in_threadpool
from starlette.datastructures import FormData, QueryParams, UploadFile
from starlette.formparsers import MultiPartException
from starlette.responses import Response as StarletteResponse

_current_request: ContextVar[Request | None] = ContextVar("jarvis_request", default=None)

_FLASK_PATH = re.compile(r"<(?:(int|float|path|string|uuid):)?(\w+)>")
_FLASK_CONV = {
    "int": "int",
    "float": "float",
    "path": "path",
    "uuid": "uuid",
}


def _starlette_path(path: str) -> str:
    def repl(match: re.Match[str]) -> str:
        conv, name = match.group(1), match.group(2)
        starlette = _FLASK_CONV.get(conv) if conv else None
        if starlette:
            return f"{{{name}:{starlette}}}"
        return f"{{{name}}}"

    return _FLASK_PATH.sub(repl, path)


def _prefer_static_routes(router: Any) -> None:
    """Flask matches a static path like /history over /<job_id> regardless of order."""
    routes = getattr(router, "routes", None)
    if not routes:
        return
    static = []
    dynamic = []
    other = []
    for route in list(routes):
        path = getattr(route, "path", None)
        if path is None:
            other.append(route)
            continue
        if "{" in path:
            dynamic.append(route)
        else:
            static.append(route)
    routes[:] = static + dynamic + other


class _FileStorage:
    def __init__(self, upload: UploadFile):
        self._upload = upload
        self.filename = upload.filename or ""

    def save(self, dst: str) -> None:
        self._upload.file.seek(0)
        with open(dst, "wb") as out:
            shutil.copyfileobj(self._upload.file, out)


class _FilesProxy:
    def _form(self) -> FormData | None:
        req = _require_request()
        return getattr(req.state, "form", None)

    def __contains__(self, key: str) -> bool:
        form = self._form()
        if not form or key not in form:
            return False
        return isinstance(form[key], UploadFile)

    def __getitem__(self, key: str) -> _FileStorage:
        form = self._form()
        if form is None or key not in form:
            raise KeyError(key)
        item = form[key]
        if not isinstance(item, UploadFile):
            raise KeyError(key)
        return _FileStorage(item)


class _FormProxy:
    def get(self, key: str, default: str | None = None) -> str | None:
        form = getattr(_require_request().state, "form", None)
        if form is None:
            return default
        value = form.get(key)
        if value is None:
            return default
        if isinstance(value, UploadFile):
            return default
        return str(value)


class _RequestProxy:
    def get_json(self, silent: bool = True, force: bool = False) -> Any:
        req = _current_request.get()
        if req is None:
            return None if silent else (_ for _ in ()).throw(RuntimeError("No request"))
        data = getattr(req.state, "json", None)
        if data is None and not silent:
            raise ValueError("No JSON body")
        return data

    @property
    def args(self) -> QueryParams:
        return _require_request().query_params

    @property
    def files(self) -> _FilesProxy:
        return _FilesProxy()

    @property
    def form(self) -> _FormProxy:
        return _FormProxy()

    @property
    def headers(self):
        return _require_request().headers

    @property
    def method(self) -> str:
        return _require_request().method


request = _RequestProxy()


def _require_request() -> Request:
    req = _current_request.get()
    if req is None:
        raise RuntimeError("No active request")
    return req


def jsonify(*args: Any, **kwargs: Any) -> JSONResponse:
    if args and kwargs:
        raise TypeError("jsonify() takes args or kwargs, not both")
    if kwargs:
        data: Any = kwargs
    elif not args:
        data = {}
    elif len(args) == 1:
        data = args[0]
    else:
        data = list(args)
    return JSONResponse(content=data)


def Response(content: Any = None, mimetype: str | None = None, headers: dict | None = None, status: int = 200):
    hdrs = dict(headers or {})
    if content is not None and not isinstance(content, (bytes, str, bytearray)) and hasattr(content, "__iter__"):
        return StreamingResponse(
            iterate_in_threadpool(content),
            media_type=mimetype,
            headers=hdrs,
            status_code=status,
        )
    return StarletteResponse(content if content is not None else b"", media_type=mimetype, headers=hdrs, status_code=status)


def make_response(body: Any):
    if isinstance(body, (JSONResponse, HTMLResponse, StarletteResponse, StreamingResponse, FileResponse)):
        return body
    return HTMLResponse(str(body))


def render_template_string(source: str, **context: Any) -> str:
    if not context:
        return source
    from jinja2 import Template
    return Template(source).render(**context)


def send_file(path: str, mimetype: str | None = None, as_attachment: bool = False, download_name: str | None = None):
    disposition = "attachment" if as_attachment else "inline"
    return FileResponse(
        path,
        media_type=mimetype,
        filename=download_name,
        content_disposition_type=disposition,
    )


def _normalize_result(result: Any) -> Any:
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        body, status = result
        if isinstance(body, JSONResponse):
            body.status_code = status
            return body
        if isinstance(body, StarletteResponse):
            body.status_code = status
            return body
        return JSONResponse(content=body, status_code=status)
    return result


def _wrap_endpoint(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapped(*args: Any, **kwargs: Any):
        return _normalize_result(func(*args, **kwargs))

    return wrapped


class Blueprint(APIRouter):
    def __init__(self, name: str, import_name: str | None = None, url_prefix: str = "", **kwargs: Any):
        super().__init__(prefix=url_prefix or "", **kwargs)
        self.name = name

    def route(self, path: str, methods: Iterable[str] | None = None, **kwargs: Any):
        methods_list = list(methods) if methods else ["GET"]
        starlette_path = _starlette_path(path)

        def decorator(func: Callable):
            wrapped = _wrap_endpoint(func)
            self.add_api_route(
                starlette_path,
                wrapped,
                methods=methods_list,
                response_model=None,
                name=f"{self.name}:{func.__name__}:{starlette_path}:{','.join(methods_list)}",
                **kwargs,
            )
            _prefer_static_routes(self)
            return func

        return decorator


class Flask(FastAPI):
    def __init__(self, import_name: str | None = None, **kwargs: Any):
        kwargs.setdefault("title", "Jarvis Agent")
        kwargs.setdefault("docs_url", "/docs")
        kwargs.setdefault("redoc_url", None)
        kwargs.setdefault("openapi_url", "/openapi.json")
        self.config: dict[str, Any] = {}
        super().__init__(**kwargs)
        self.add_middleware(_FlaskCompatMiddleware, flask_app=self)

    def route(self, path: str, methods: Iterable[str] | None = None, **kwargs: Any):
        methods_list = list(methods) if methods else ["GET"]
        starlette_path = _starlette_path(path)

        def decorator(func: Callable):
            wrapped = _wrap_endpoint(func)
            self.add_api_route(
                starlette_path,
                wrapped,
                methods=methods_list,
                response_model=None,
                name=f"{func.__name__}:{starlette_path}:{','.join(methods_list)}",
                **kwargs,
            )
            _prefer_static_routes(self.router)
            return func

        return decorator

    def register_blueprint(self, bp: APIRouter, **kwargs: Any) -> None:
        self.include_router(bp, **kwargs)
        _prefer_static_routes(self.router)

    def test_client(self):
        return _FlaskTestClient(self)


def _content_length(headers) -> int | None:
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class _FlaskCompatMiddleware:
    def __init__(self, app: Any, flask_app: Flask | None = None):
        self.app = app
        self.flask_app = flask_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive, send)
        max_len = None
        if self.flask_app is not None:
            max_len = self.flask_app.config.get("MAX_CONTENT_LENGTH")
        if isinstance(max_len, int) and max_len > 0:
            clen = _content_length(request.headers)
            if clen is not None and clen > max_len:
                too_large = JSONResponse({"error": "Request entity too large"}, status_code=413)
                await too_large(scope, receive, send)
                return
            if request.method in ("POST", "PUT", "PATCH"):
                body = await request.body()
                if len(body) > max_len:
                    too_large = JSONResponse({"error": "Request entity too large"}, status_code=413)
                    await too_large(scope, receive, send)
                    return

        ctype = (request.headers.get("content-type") or "").lower()
        request.state.json = None
        request.state.form = None
        if "application/json" in ctype:
            try:
                request.state.json = await request.json()
            except Exception:
                request.state.json = None
        elif "application/x-www-form-urlencoded" in ctype:
            try:
                request.state.form = await request.form()
            except Exception:
                request.state.form = None
        elif "multipart/form-data" in ctype:
            part_size = max_len if isinstance(max_len, int) and max_len > 0 else 1024 * 1024
            try:
                request.state.form = await request.form(max_part_size=part_size)
            except TypeError:
                request.state.form = await request.form()
            except MultiPartException:
                too_large = JSONResponse({"error": "Request entity too large"}, status_code=413)
                await too_large(scope, receive, send)
                return
            except Exception as exc:
                detail = str(getattr(exc, "detail", exc))
                if "exceeded" in detail.lower() or "too large" in detail.lower():
                    too_large = JSONResponse({"error": "Request entity too large"}, status_code=413)
                    await too_large(scope, receive, send)
                    return
                request.state.form = None

        token = _current_request.set(request)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_request.reset(token)
            form = getattr(request.state, "form", None)
            if form is not None:
                try:
                    await form.close()
                except Exception:
                    pass


class _FlaskTestResponse:
    def __init__(self, response: Any):
        self._response = response

    def get_json(self, silent: bool = True) -> Any:
        try:
            return self._response.json()
        except Exception:
            if silent:
                return None
            raise

    @property
    def data(self) -> bytes:
        return self._response.content

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self):
        return self._response.headers

    @property
    def text(self) -> str:
        return self._response.text

    def json(self) -> Any:
        return self._response.json()


class _FlaskTestClient:
    def __init__(self, app: FastAPI):
        from fastapi.testclient import TestClient

        self._client = TestClient(app)

    def get(self, url: str, query_string: Any = None, **kwargs: Any):
        params = kwargs.pop("params", None)
        if query_string is not None:
            params = query_string
        return _FlaskTestResponse(self._client.get(url, params=params, **kwargs))

    def post(self, url: str, json: Any = None, data: Any = None, content_type: str | None = None, **kwargs: Any):
        headers = dict(kwargs.pop("headers", None) or {})
        if content_type:
            headers["Content-Type"] = content_type
        files = kwargs.pop("files", None)
        return _FlaskTestResponse(
            self._client.post(
                url,
                json=json,
                data=data,
                files=files,
                headers=headers or None,
                **kwargs,
            )
        )

    def put(self, url: str, json: Any = None, **kwargs: Any):
        return _FlaskTestResponse(self._client.put(url, json=json, **kwargs))

    def delete(self, url: str, **kwargs: Any):
        return _FlaskTestResponse(self._client.delete(url, **kwargs))
