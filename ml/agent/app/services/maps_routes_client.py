from __future__ import annotations

import math
from typing import Any, Dict, List

import httpx

from app.settings import settings


def _offset_latlng(lat: float, lng: float, distance_km: float, heading_deg: float) -> Dict[str, float]:
    """Roughly offset a point by distance_km toward heading_deg."""
    earth_radius_km = 6371.0
    heading_rad = math.radians(heading_deg)
    delta = distance_km / earth_radius_km

    lat_rad = math.radians(lat)
    lng_rad = math.radians(lng)

    new_lat = math.asin(
        math.sin(lat_rad) * math.cos(delta) + math.cos(lat_rad) * math.sin(delta) * math.cos(heading_rad)
    )
    new_lng = lng_rad + math.atan2(
        math.sin(heading_rad) * math.sin(delta) * math.cos(lat_rad),
        math.cos(delta) - math.sin(lat_rad) * math.sin(new_lat),
    )
    return {"lat": math.degrees(new_lat), "lng": math.degrees(new_lng)}


async def compute_route_candidates(
    *,
    request_id: str,
    start_lat: float,
    start_lng: float,
    distance_km: float,
    round_trip: bool,
) -> List[Dict[str, Any]]:
    """
    Call Routes API to build a few candidate routes.
    Uses simple geometric offsets to propose destinations, then asks Routes API
    for walking directions. Falls back to empty list if API key not set.
    """
    api_key = settings.MAPS_API_KEY
    if not api_key:
        raise RuntimeError("MAPS_API_KEY is not configured")

    # Create 3 headings to diversify candidates
    headings = [0, 120, -120]
    dests = [
        _offset_latlng(start_lat, start_lng, max(distance_km, 0.5), h)
        for h in headings
    ]

    headers = {
        "X-Goog-Api-Key": api_key,
        # Limit fields to reduce payload size
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline",
    }

    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SEC) as client:
        results: List[Dict[str, Any]] = []
        for idx, dest in enumerate(dests, start=1):
            body = {
                "origin": {"location": {"latLng": {"latitude": start_lat, "longitude": start_lng}}},
                "destination": {"location": {"latLng": {"latitude": dest["lat"], "longitude": dest["lng"]}}},
                "travelMode": "WALK",
                "routingPreference": "NEUTRAL",
                "computeAlternativeRoutes": False,
                "routeModifiers": {"avoidTolls": True, "avoidHighways": True, "avoidFerries": True},
            }
            if round_trip:
                # Encourage a loop by using the start point as an intermediate
                body["intermediates"] = [{"location": {"latLng": {"latitude": start_lat, "longitude": start_lng}}}]
            resp = await client.post(settings.MAPS_ROUTES_BASE, json=body, headers=headers)
            if resp.status_code != 200:
                continue
            data = resp.json()
            routes = data.get("routes", [])
            if not routes:
                continue
            r0 = routes[0]
            encoded = r0.get("polyline", {}).get("encodedPolyline")
            distance_m = r0.get("distanceMeters")
            duration = r0.get("duration")
            # duration is like "123s"
            duration_sec = 0.0
            if isinstance(duration, str) and duration.endswith("s"):
                try:
                    duration_sec = float(duration[:-1])
                except ValueError:
                    duration_sec = 0.0
            if encoded and distance_m is not None:
                results.append({
                    "route_id": f"route_{idx}",
                    "polyline": encoded,
                    "distance_km": float(distance_m) / 1000.0,
                    "duration_min": duration_sec / 60.0 if duration_sec else None,
                })
        return results
