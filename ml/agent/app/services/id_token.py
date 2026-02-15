"""
Cloud Run IAM 認証用の OIDC ID Token 取得。
audience（例: Ranker のベースURL）を指定して ID Token を返し、TTL キャッシュで再利用する。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ID Token は通常 1 時間有効。exp まで使うため 55 分でキャッシュ失効させる。
_ID_TOKEN_TTL_SEC = 55 * 60
_ID_TOKEN_CACHE: Optional[TTLCache[str, str]] = None


def _get_id_token_cache() -> TTLCache[str, str]:
    global _ID_TOKEN_CACHE
    if _ID_TOKEN_CACHE is None:
        _ID_TOKEN_CACHE = TTLCache(maxsize=32, ttl=_ID_TOKEN_TTL_SEC)
    return _ID_TOKEN_CACHE


def _cache_key(audience: str) -> str:
    return f"idtoken:{audience}"


def get_id_token_sync(audience: str) -> str:
    """
    audience 向けの OIDC ID Token を取得する（同期）。
    Cloud Run / GCE 上ではメタデータ経由で取得。ローカルでは GOOGLE_APPLICATION_CREDENTIALS 等。
    """
    cache = _get_id_token_cache()
    key = _cache_key(audience)
    cached = cache.get(key)
    if cached is not None:
        return cached

    import google.auth.transport.requests
    import google.oauth2.id_token

    request = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(request, audience)
    cache[key] = token
    return token


async def get_id_token_async(audience: str) -> str:
    """
    audience 向けの ID Token を非同期で取得する。
    取得は同期 API のため asyncio.to_thread で実行する。
    """
    return await asyncio.to_thread(get_id_token_sync, audience)


async def get_token(audience: str) -> str:
    """get_id_token_async のエイリアス（Ranker 呼び出し用）。"""
    return await get_id_token_async(audience)
