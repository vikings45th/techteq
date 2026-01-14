from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)


def _get_place_types_for_theme(theme: str) -> List[str]:
    """
    themeに応じたPlaces APIの場所タイプを返す。
    各themeに「それっぽい」体験を提供するための場所タイプをマッピング。
    """
    theme_to_types: Dict[str, List[str]] = {
        "exercise": [
            "park",  # 公園（運動に適した場所）
            "gym",  # ジム
            "sports_complex",  # スポーツ施設
            "fitness_center",  # フィットネスセンター
            "hiking_area",  # ハイキングエリア
            "cycling_park",  # サイクリングパーク
            "stadium",  # スタジアム
        ],
        "think": [
            "park",  # 公園（静かな思考に適した場所）
            "library",  # 図書館
            "museum",  # 博物館
            "cafe",  # カフェ
            "temple",  # 寺院
            "shrine",  # 神社
            "art_gallery",  # 美術館
        ],
        "refresh": [
            "park",  # 公園（気分転換に適した場所）
            "cafe",  # カフェ
            "restaurant",  # レストラン
            "viewpoint",  # 展望台
            "scenic_overlook",  # 景色の良い場所
            "beach",  # ビーチ
            "waterfall",  # 滝
        ],
        "nature": [
            "park",  # 公園
            "national_park",  # 国立公園
            "state_park",  # 州立公園
            "hiking_area",  # ハイキングエリア
            "nature_reserve",  # 自然保護区
            "botanical_garden",  # 植物園
            "forest",  # 森
            "lake",  # 湖
        ],
    }
    return theme_to_types.get(theme, ["park"])  # デフォルトは公園


async def search_spots(
    *,
    lat: float,
    lng: float,
    theme: Optional[str] = None,
    radius_m: int = 1500,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fetch nearby places filtered by theme. Returns a small list of {name, type, place_id}.
    
    Args:
        lat: 緯度
        lng: 経度
        theme: テーマ（"exercise", "think", "refresh", "nature"）
        radius_m: 検索半径（メートル）
        max_results: 最大結果数
    
    Returns:
        場所のリスト（name, type, place_idを含む）
    """
    api_key = settings.MAPS_API_KEY
    if not api_key:
        logger.warning("[Places API] MAPS_API_KEY is not configured")
        return []

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.types",
    }
    body = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
        "maxResultCount": min(max_results, 20),  # maxResultCountは1-20の範囲
    }
    
    # themeが指定されている場合、includedTypesでフィルタリング
    # ただし、結果が空の場合はフォールバックとしてincludedTypesなしで検索
    use_theme_filter = False
    if theme:
        included_types = _get_place_types_for_theme(theme)
        body["includedTypes"] = included_types
        use_theme_filter = True
        logger.debug(
            "[Places API] Searching with theme=%s types=%s",
            theme,
            included_types,
        )

    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SEC) as client:
            resp = await client.post(settings.MAPS_PLACES_BASE, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "[Places API] HTTP error: status=%d response=%s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []
            data = resp.json()
            places = data.get("places", [])
            out: List[Dict[str, Any]] = []
            for p in places[:max_results]:
                name = p.get("displayName", {}).get("text")
                place_id = p.get("id")  # place_idを取得
                types = p.get("types") or []
                primary = types[0] if types else "unknown"
                if name:
                    out.append({"name": name, "type": primary, "place_id": place_id})
            
            # themeフィルタを使用したが結果が空の場合、フォールバックとしてincludedTypesなしで再検索
            if use_theme_filter and len(out) == 0:
                logger.info(
                    "[Places API] No results with theme filter, falling back to unfiltered search"
                )
                body_fallback = body.copy()
                body_fallback.pop("includedTypes", None)
                resp_fallback = await client.post(settings.MAPS_PLACES_BASE, json=body_fallback, headers=headers)
                if resp_fallback.status_code == 200:
                    data_fallback = resp_fallback.json()
                    places_fallback = data_fallback.get("places", [])
                    for p in places_fallback[:max_results]:
                        name = p.get("displayName", {}).get("text")
                        place_id = p.get("id")
                        types = p.get("types") or []
                        primary = types[0] if types else "unknown"
                        if name:
                            out.append({"name": name, "type": primary, "place_id": place_id})
            
            logger.info(
                "[Places API] Found %d places near (%.6f, %.6f) theme=%s",
                len(out),
                lat,
                lng,
                theme or "any",
            )
            return out
    except httpx.TimeoutException as e:
        logger.warning("[Places API] Timeout: lat=%.6f lng=%.6f err=%r", lat, lng, e)
        return []
    except Exception as e:
        logger.exception("[Places API] Error: lat=%.6f lng=%.6f err=%r", lat, lng, e)
        return []
