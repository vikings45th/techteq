from __future__ import annotations

from typing import Any, Dict, List
import logging

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)


async def search_spots(
    *,
    lat: float,
    lng: float,
    radius_m: int = 1500,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fetch nearby places. Returns a small list of {name, type}.
    """
    api_key = settings.MAPS_API_KEY
    if not api_key:
        logger.warning("[Places API] MAPS_API_KEY is not configured")
        return []

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.types",
    }
    body = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
        "pageSize": max_results,
    }

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
                types = p.get("types") or []
                primary = types[0] if types else "unknown"
                if name:
                    out.append({"name": name, "type": primary})
            logger.info("[Places API] Found %d places near (%.6f, %.6f)", len(out), lat, lng)
            return out
    except httpx.TimeoutException as e:
        logger.warning("[Places API] Timeout: lat=%.6f lng=%.6f err=%r", lat, lng, e)
        return []
    except Exception as e:
        logger.exception("[Places API] Error: lat=%.6f lng=%.6f err=%r", lat, lng, e)
        return []
