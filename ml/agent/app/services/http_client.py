from __future__ import annotations

from typing import Optional
import httpx


_http_client: Optional[httpx.AsyncClient] = None


def set_client(client: Optional[httpx.AsyncClient]) -> None:
    global _http_client
    _http_client = client


def get_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client is not initialized")
    return _http_client
