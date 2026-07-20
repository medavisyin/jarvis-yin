"""
网络策略 — 拉数据前探测直连/代理，缓存探测结果.

避免盲目走代理或反复撞东财频控。
"""
import json
import logging
import os
import time

import requests

from config import STOCK_CACHE_DIR, STOCK_PROXY

log = logging.getLogger(__name__)

_CACHE_DIR = os.path.join(STOCK_CACHE_DIR, ".network")
_PROBE_CACHE = os.path.join(_CACHE_DIR, "probe.json")
_PROBE_TTL_SEC = 1800
_PROBE_URL = "https://hq.sinajs.cn/list=sh600519"
_PROBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}

_last_mode: str | None = None


def _load_cached_probe() -> dict | None:
    if not os.path.isfile(_PROBE_CACHE):
        return None
    try:
        with open(_PROBE_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) < _PROBE_TTL_SEC:
            return data
    except Exception:
        pass
    return None


def _save_probe(data: dict):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    data["ts"] = time.time()
    with open(_PROBE_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _try_request(proxies: dict | None, timeout: float = 8) -> bool:
    try:
        r = requests.get(
            _PROBE_URL, headers=_PROBE_HEADERS, timeout=timeout, proxies=proxies,
        )
        return r.status_code == 200 and "600519" in r.text
    except Exception:
        return False


def probe_network(force: bool = False) -> dict:
    """
    探测直连 vs 代理，返回 {mode, proxies, direct_ok, proxy_ok}.
    mode: direct | proxy | none
    """
    global _last_mode
    if not force:
        cached = _load_cached_probe()
        if cached:
            _last_mode = cached.get("mode")
            return cached

    direct_ok = _try_request(None)
    proxy_ok = False
    proxy_dict = None
    if STOCK_PROXY:
        proxy_dict = {"http": STOCK_PROXY, "https": STOCK_PROXY}
        proxy_ok = _try_request(proxy_dict)

    if direct_ok:
        mode = "direct"
        proxies = None
    elif proxy_ok:
        mode = "proxy"
        proxies = proxy_dict
    else:
        mode = "none"
        proxies = proxy_dict if STOCK_PROXY else None

    result = {
        "mode": mode,
        "proxies": proxies,
        "direct_ok": direct_ok,
        "proxy_ok": proxy_ok,
        "proxy_configured": bool(STOCK_PROXY),
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_probe(result)
    _last_mode = mode
    log.info(
        "网络探测: mode=%s direct=%s proxy=%s",
        mode, direct_ok, proxy_ok,
    )
    return result


def get_proxies(force_probe: bool = False) -> dict | None:
    """供 requests / akshare 使用的 proxies 参数."""
    info = probe_network(force=force_probe)
    return info.get("proxies")


def get_network_mode() -> str:
    """当前推荐网络模式."""
    global _last_mode
    if _last_mode is None:
        probe_network()
    return _last_mode or "none"


def ensure_network(force: bool = False) -> bool:
    """拉数据前调用；无可用链路时返回 False."""
    info = probe_network(force=force)
    if info["mode"] == "none":
        log.warning("网络探测: 直连与代理均不可用")
        return False
    return True
