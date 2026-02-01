from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import random

import httpx

from app.settings import settings
from app.services.http_client import get_client

logger = logging.getLogger(__name__)


def _get_place_types_for_theme(theme: str) -> List[str]:
    """
    themeに応じたPlaces APIの場所タイプを返す。
    各themeに「それっぽい」体験を提供するための場所タイプをマッピング。
    """
    theme_to_types: Dict[str, List[str]] = {
        "exercise": [
            "park",  # 公園（体を使って整える）
            "sports_complex",  # スポーツ施設
            "hiking_area",  # ハイキングエリア
            "cycling_park",  # サイクリングパーク
            "stadium",  # スタジアム
            "sports_club",  # スポーツクラブ
            "sports_activity_location",  # スポーツ活動場所
            "swimming_pool",  # プール
            "athletic_field",  # 運動場
            "playground",  # 遊び場
            "arena",  # アリーナ
        ],
        "think": [
            "park",  # 静かな道
            "garden",  # 庭園
            "botanical_garden",  # 植物園
            "plaza",  # 広場
            "observation_deck",  # 展望台
        ],
        "refresh": [
            "park",  # 景色の変化
            "plaza",  # 広場
            "observation_deck",  # 展望台
            "garden",  # 庭園
            "botanical_garden",  # 植物園
            "tourist_attraction",  # 観光スポット（景観寄り）
        ],
        "nature": [
            "park",  # 公園
            "national_park",  # 国立公園
            "state_park",  # 州立公園
            "hiking_area",  # ハイキングエリア
            "botanical_garden",  # 植物園
            "garden",  # 庭園
            "beach",  # ビーチ
            "wildlife_park",  # 野生動物公園
            "wildlife_refuge",  # 野生動物保護区
        ],
    }
    return theme_to_types.get(theme, ["park"])  # デフォルトは公園


def _get_hidden_keywords_for_theme(theme: str) -> List[str]:
    theme_to_keywords: Dict[str, List[str]] = {
        "exercise": ["整える", "リセット", "体を動かす"],
        "think": ["ぼーっと", "無心", "静かな道"],
        "refresh": ["景色", "気分転換", "寄り道"],
        "nature": ["深呼吸", "緑", "木漏れ日"],
    }
    return theme_to_keywords.get(theme, ["穴場"])


def _get_classic_place_types_for_theme(theme: str) -> List[str]:
    theme_to_types: Dict[str, List[str]] = {
        "exercise": ["park", "sports_complex", "athletic_field", "hiking_area"],
        "think": ["park", "garden", "botanical_garden", "plaza"],
        "refresh": ["park", "observation_deck", "plaza", "garden", "botanical_garden"],
        "nature": ["park", "national_park", "botanical_garden", "garden", "beach", "hiking_area"],
    }
    return theme_to_types.get(theme, ["park"])


def pick_hidden_keyword(theme: Optional[str]) -> Optional[str]:
    if not theme:
        return None
    options = _get_hidden_keywords_for_theme(theme)
    return random.choice(options) if options else None


def get_classic_place_types_for_theme(theme: Optional[str]) -> List[str]:
    if not theme:
        return []
    return _get_classic_place_types_for_theme(theme)


def _blocklist_names() -> List[str]:
    raw = str(getattr(settings, "PLACES_NAME_BLOCKLIST", "") or "")
    return [w.strip() for w in raw.split(",") if w.strip()]


def _blocklist_types() -> List[str]:
    raw = str(getattr(settings, "PLACES_TYPE_BLOCKLIST", "") or "")
    return [w.strip() for w in raw.split(",") if w.strip()]


def _normalize_name(name: str) -> str:
    return name.replace(" ", "").replace("　", "").lower()


def _is_blocked_place(name: Optional[str], primary_type: Optional[str]) -> bool:
    if primary_type:
        if primary_type in _blocklist_types():
            return True
    if not name:
        return False
    n = _normalize_name(name)
    for w in _blocklist_names():
        if _normalize_name(w) in n:
            return True
    return False


async def search_spots(
    *,
    lat: float,
    lng: float,
    theme: Optional[str] = None,
    radius_m: int = 1500,
    max_results: int = 5,
    included_types: Optional[List[str]] = None,
    keyword: Optional[str] = None,
    allow_unfiltered_fallback: bool = True,
) -> List[Dict[str, Any]]:
    """
    Fetch nearby places filtered by theme. Returns a small list of {name, type, place_id}.
    Optionally applies included types and a keyword for discovery-focused search.
    
    Args:
        lat: 緯度
        lng: 経度
        theme: テーマ（"exercise", "think", "refresh", "nature"）
        radius_m: 検索半径（メートル）
        max_results: 最大結果数
        included_types: 明示的に指定する場所タイプ
        keyword: 日本語キーワード（穴場検索用）
        allow_unfiltered_fallback: テーマフィルタなし検索へのフォールバック可否
    
    Returns:
        場所のリスト（name, type, place_idを含む）
    """
    api_key = settings.MAPS_API_KEY
    if not api_key:
        logger.warning("[Places API] MAPS_API_KEY is not configured")
        return []
    
    logger.debug(
        "[Places API] Starting search: lat=%.6f lng=%.6f theme=%s radius_m=%d max_results=%d",
        lat,
        lng,
        theme,
        radius_m,
        max_results,
    )

    field_mask = "places.id,places.displayName,places.types,places.location"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }
    body = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
        "maxResultCount": min(max_results, 20),  # maxResultCountは1-20の範囲
        "languageCode": "ja",  # 日本語でレスポンスを取得
    }
    
    # themeが指定されている場合、includedTypesでフィルタリング
    # ただし、結果が空の場合はフォールバックとしてincludedTypesなしで検索
    use_theme_filter = False  # テーマフィルタを使用したかどうかのフラグ
    if included_types:
        body["includedTypes"] = included_types  # 明示的に指定された場所タイプ
        use_theme_filter = True
    elif theme:
        included_types = _get_place_types_for_theme(theme)  # テーマに応じた場所タイプを取得
        body["includedTypes"] = included_types  # リクエストボディに場所タイプを追加
        use_theme_filter = True
        logger.debug(
            "[Places API] Searching with theme=%s types=%s",
            theme,
            included_types,
        )
    if keyword:
        body["keyword"] = keyword

    try:
        client = get_client()
        resp = await client.post(settings.MAPS_PLACES_BASE, json=body, headers=headers)
        if resp.status_code != 200:
            if resp.status_code == 400 and keyword:
                logger.info(
                    "[Places API] Keyword rejected, retrying without keyword. keyword=%s",
                    keyword,
                )
                body_retry = body.copy()
                body_retry.pop("keyword", None)
                resp = await client.post(settings.MAPS_PLACES_BASE, json=body_retry, headers=headers)
                body = body_retry
            if resp.status_code != 200:
                logger.warning(
                    "[Places API] HTTP error: status=%d response=%s body=%s",
                    resp.status_code,
                    resp.text[:500],
                    str(body)[:500],
                )
                return []

        data = resp.json()
        places = data.get("places", [])  # レスポンスから場所リストを取得
        out: List[Dict[str, Any]] = []
        # 各場所から必要な情報を抽出
        for p in places[:max_results]:
            name = p.get("displayName", {}).get("text")  # 表示名を取得
            place_id = p.get("id")  # place_idを取得
            types = p.get("types") or []  # 場所タイプのリスト
            primary = types[0] if types else "unknown"  # 最初のタイプを主要タイプとする
            location = p.get("location") or {}
            lat = location.get("latitude")
            lng = location.get("longitude")
            if _is_blocked_place(name, primary):
                continue
            if name and lat is not None and lng is not None:
                out.append(
                    {
                        "name": name,
                        "type": primary,
                        "place_id": place_id,
                        "lat": float(lat),
                        "lng": float(lng),
                    }
                )
            
        # themeフィルタを使用したが結果が空の場合、フォールバックとしてincludedTypesなしで再検索
        if allow_unfiltered_fallback and use_theme_filter and len(out) == 0:
            logger.info(
                "[Places API] No results with theme filter, falling back to unfiltered search"
            )
            body_fallback = body.copy()
            body_fallback.pop("includedTypes", None)
            resp_fallback = await client.post(settings.MAPS_PLACES_BASE, json=body_fallback, headers=headers)
            if resp_fallback.status_code == 200:
                data_fallback = resp_fallback.json()
                places_fallback = data_fallback.get("places", [])
                logger.info(
                    "[Places API] Fallback search returned %d places",
                    len(places_fallback),
                )
                for p in places_fallback[:max_results]:
                    name = p.get("displayName", {}).get("text")
                    place_id = p.get("id")
                    types = p.get("types") or []
                    primary = types[0] if types else "unknown"
                    location = p.get("location") or {}
                    lat = location.get("latitude")
                    lng = location.get("longitude")
                    if _is_blocked_place(name, primary):
                        continue
                    if name and lat is not None and lng is not None:
                        out.append(
                            {
                                "name": name,
                                "type": primary,
                                "place_id": place_id,
                                "lat": float(lat),
                                "lng": float(lng),
                            }
                        )
            else:
                logger.warning(
                    "[Places API] Fallback search HTTP error: status=%d response=%s",
                    resp_fallback.status_code,
                    resp_fallback.text[:200],
                )

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
