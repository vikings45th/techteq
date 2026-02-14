"""
/route/generate 用のインプロセスTTLキャッシュ。
同一条件の連続リクエスト時に Maps/Ranker/LLM を呼ばず即時レスポンスする。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from cachetools import TTLCache

from app.schemas import GenerateRouteRequest
from app.settings import settings

logger = logging.getLogger(__name__)

# キャッシュ本体（設定で有効時のみ使用、遅延初期化）
_ttl_cache: Optional[TTLCache[str, Dict[str, Any]]] = None
# key ごとの Lock（同一キーの並行リクエストで生成を1回に集約）
_key_locks: Dict[str, asyncio.Lock] = {}
_lock_for_locks: asyncio.Lock = asyncio.Lock()


def _get_cache() -> TTLCache[str, Dict[str, Any]]:
    """設定に従いキャッシュを返す。無効時は None を返さず maxsize=0 相当にしないため、呼び出し元で GENERATE_CACHE_ENABLED を確認する。"""
    global _ttl_cache
    if _ttl_cache is None:
        _ttl_cache = TTLCache(
            maxsize=max(1, settings.GENERATE_CACHE_MAXSIZE),
            ttl=settings.GENERATE_CACHE_TTL_SEC,
        )
    return _ttl_cache


def build_cache_key(req: GenerateRouteRequest) -> str:
    """
    request_id を除いた入力条件からキャッシュキーを生成する。
    lat/lng は丸め、distance_km は 0.1km 刻みで揃え、JSON の sha256 で安定した短いキーにする。
    """
    lat_dec = getattr(
        settings, "GENERATE_CACHE_ROUND_LATLNG_DECIMALS", 5
    )
    dist_dec = getattr(
        settings, "GENERATE_CACHE_ROUND_DISTANCE_DECIMALS", 1
    )
    slat = round(req.start_location.lat, lat_dec)
    slng = round(req.start_location.lng, lat_dec)
    if req.end_location is not None:
        e = [round(req.end_location.lat, lat_dec), round(req.end_location.lng, lat_dec)]
    else:
        e = None
    payload = {
        "v": 1,
        "theme": req.theme,
        "d": round(req.distance_km, dist_dec),
        "rt": req.round_trip,
        "s": [slat, slng],
        "e": e,
    }
    canonical = json.dumps(payload, sort_keys=True)
    h = hashlib.sha256(canonical.encode()).hexdigest()
    return "gen:v1:" + h


async def _get_key_lock(key: str) -> asyncio.Lock:
    """key 用の Lock を取得する（同一キーで並行リクエストを1本化するため）。"""
    async with _lock_for_locks:
        if key not in _key_locks:
            _key_locks[key] = asyncio.Lock()
        return _key_locks[key]


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    """キャッシュからレスポンス辞書を取得する。ヒットしなければ None。"""
    if not getattr(settings, "GENERATE_CACHE_ENABLED", True):
        return None
    try:
        cache = _get_cache()
        return cache.get(key)
    except Exception as e:
        logger.warning("generate cache get error key=%s err=%s", key[:16], e)
        return None


def cache_set(key: str, response_dict: Dict[str, Any]) -> None:
    """レスポンス辞書をキャッシュに保存する。best-effort。"""
    if not getattr(settings, "GENERATE_CACHE_ENABLED", True):
        return
    try:
        cache = _get_cache()
        cache[key] = response_dict
    except Exception as e:
        logger.warning("generate cache set error key=%s err=%s", key[:16], e)


def cache_key_prefix(key: str, length: int = 8) -> str:
    """ログ用にキーの先頭を返す（gen:v1: を除いたハッシュ部分）。"""
    prefix = "gen:v1:"
    if key.startswith(prefix):
        return key[len(prefix) : len(prefix) + length]
    return key[:length]
