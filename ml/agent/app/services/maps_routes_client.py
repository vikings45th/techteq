from __future__ import annotations

import math
import logging
from typing import Any, Dict, List

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)


async def _calculate_elevation_gain(encoded_polyline: str, api_key: str) -> float:
    """
    Elevation APIを使用して標高差を計算
    
    Args:
        encoded_polyline: エンコードされたpolyline
        api_key: Google Maps APIキー
    
    Returns:
        累積標高差（m、上り方向のみ）
    """
    try:
        # Elevation APIのエンドポイント
        elevation_url = "https://maps.googleapis.com/maps/api/elevation/json"
        
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SEC) as client:
            params = {
                "locations": f"enc:{encoded_polyline}",
                "key": api_key,
            }
            resp = await client.get(elevation_url, params=params)
            
            if resp.status_code != 200:
                logger.warning(f"[Elevation API] HTTP error: status={resp.status_code}")
                return 0.0
            
            data = resp.json()
            if data.get("status") != "OK":
                logger.warning(f"[Elevation API] API error: {data.get('status')}")
                return 0.0
            
            results = data.get("results", [])
            if len(results) < 2:
                return 0.0
            
            # 累積標高差を計算（上り方向のみ）
            elevation_gain = 0.0
            prev_elevation = results[0].get("elevation", 0.0)
            
            for result in results[1:]:
                current_elevation = result.get("elevation", 0.0)
                elevation_diff = current_elevation - prev_elevation
                if elevation_diff > 0:  # 上り方向のみ
                    elevation_gain += elevation_diff
                prev_elevation = current_elevation
            
            return elevation_gain
            
    except Exception as e:
        logger.warning(f"[Elevation API] Error calculating elevation gain: {e}", exc_info=True)
        return 0.0


def _offset_latlng(lat: float, lng: float, distance_km: float, heading_deg: float) -> Dict[str, float]:
    """
    指定された距離と方向に基づいて、緯度経度の点をオフセットする
    
    大円距離の計算を使用して、開始点から指定された距離と方向（方位角）に移動した点を計算する。
    
    Args:
        lat: 開始点の緯度
        lng: 開始点の経度
        distance_km: 移動距離（km）
        heading_deg: 方位角（度、0°が北、時計回り）
    
    Returns:
        オフセットされた点の緯度経度 {"lat": float, "lng": float}
    """
    earth_radius_km = 6371.0  # 地球の半径（km）
    heading_rad = math.radians(heading_deg)  # 方位角をラジアンに変換
    delta = distance_km / earth_radius_km  # 角度差（ラジアン）

    lat_rad = math.radians(lat)  # 緯度をラジアンに変換
    lng_rad = math.radians(lng)  # 経度をラジアンに変換

    # 新しい緯度を計算（球面三角法を使用）
    new_lat = math.asin(
        math.sin(lat_rad) * math.cos(delta) + math.cos(lat_rad) * math.sin(delta) * math.cos(heading_rad)
    )
    # 新しい経度を計算
    new_lng = lng_rad + math.atan2(
        math.sin(heading_rad) * math.sin(delta) * math.cos(lat_rad),
        math.cos(delta) - math.sin(lat_rad) * math.sin(new_lat),
    )
    return {"lat": math.degrees(new_lat), "lng": math.degrees(new_lng)}  # 度に変換して返す


async def compute_route_candidates(
    *,
    request_id: str,
    start_lat: float,
    start_lng: float,
    end_lat: float | None = None,
    end_lng: float | None = None,
    distance_km: float,
    round_trip: bool,
) -> List[Dict[str, Any]]:
    """
    Routes APIを呼び出して複数のルート候補を生成する
    
    シンプルな幾何学的オフセットを使用して目的地を提案し、
    Routes APIに歩行ルートを問い合わせる。
    APIキーが設定されていない場合は空リストを返す。
    
    Args:
        request_id: リクエストID（ログ用）
        start_lat: 開始地点の緯度
        start_lng: 開始地点の経度
        end_lat: 終了地点の緯度（片道ルート用）
        end_lng: 終了地点の経度（片道ルート用）
        distance_km: 目標距離（km）
        round_trip: 往復ルートかどうか
    
    Returns:
        ルート候補のリスト [{"route_id": str, "polyline": str, "distance_km": float, ...}, ...]
    
    Raises:
        RuntimeError: MAPS_API_KEYが設定されていない場合
    """
    api_key = settings.MAPS_API_KEY
    if not api_key:
        raise RuntimeError("MAPS_API_KEY is not configured")

    # 候補を多様化するために5つの方位角を作成（360°を5等分）
    # 0°, 72°, 144°, 216° (=-144°), 288° (=-72°) で均等に配置
    headings = [0, 72, 144, -144, -72]

    # 片道かつ終了地点が指定されている場合は、その地点を目的地として使用
    if not round_trip and end_lat is not None and end_lng is not None:
        dests = [{"lat": float(end_lat), "lng": float(end_lng)}]
    else:
        # 往復ルートの場合、計算された点を*折り返し地点*として使用
        # distance_kmが目標の*ループ距離*の場合、折り返し地点は約半分の距離
        waypoint_distance_km = max((distance_km / 2.0) if round_trip else distance_km, 0.5)
        # 各方位角に対して目的地を計算
        dests = [_offset_latlng(start_lat, start_lng, waypoint_distance_km, h) for h in headings]
    
    headers = {
        "X-Goog-Api-Key": api_key,
        # Include steps for stairway detection and elevation data
        # Note: routes.legs must be included to access routes.legs.steps
        # stepType field doesn't exist in Routes API v2, so we request the full steps object
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline,routes.legs,routes.legs.steps,routes.legs.steps.navigationInstruction",
    }

    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SEC) as client:
        results: List[Dict[str, Any]] = []
        for idx, dest in enumerate(dests, start=1):
            travel_mode = "WALK"
            body = {
                "origin": {"location": {"latLng": {"latitude": start_lat, "longitude": start_lng}}},
                "travelMode": travel_mode,
                "computeAlternativeRoutes": False,
                # WALKでは routeModifiers を送らない
            }

            if travel_mode in ("DRIVE", "TWO_WHEELER"):
                body["routeModifiers"] = {
                    "avoidTolls": True,
                    "avoidHighways": True,
                    "avoidFerries": True,
                }

            if round_trip:
                # Loop route: start -> (turnaround waypoint) -> start
                body["destination"] = {"location": {"latLng": {"latitude": start_lat, "longitude": start_lng}}}
                body["intermediates"] = [
                    {"location": {"latLng": {"latitude": dest["lat"], "longitude": dest["lng"]}}}
                ]
            else:
                body["destination"] = {"location": {"latLng": {"latitude": dest["lat"], "longitude": dest["lng"]}}}
            
            # リクエストのログ出力（デバッグ用）
            logger.debug(
                "[Routes API Request] request_id=%s route_%d origin=(%.6f,%.6f) dest=(%.6f,%.6f) round_trip=%s",
                request_id,
                idx,
                start_lat,
                start_lng,
                dest["lat"],
                dest["lng"],
                round_trip,
            )
            
            resp = await client.post(settings.MAPS_ROUTES_BASE, json=body, headers=headers)
            
            # 200以外のstatus / response bodyを必ずログ出力
            if resp.status_code != 200:
                logger.warning(
                    "[Routes API Error] request_id=%s status=%d body=%s",
                    request_id,
                    resp.status_code,
                    resp.text[:500],
                )
                # 400エラーの場合はその場で打ち切り
                if resp.status_code == 400:
                    return []
                continue

            try:
                data = resp.json()
            except Exception as e:
                logger.error("[Routes API Error] JSON Parse Failed. request_id=%s err=%r", request_id, e)
                continue
            
            # レスポンスの構造をログ出力（デバッグ用）
            if "error" in data:
                logger.warning(
                    "[Routes API Error] request_id=%s error=%s",
                    request_id,
                    data.get("error", {}),
                )
                continue
            
            routes = data.get("routes", [])
            if not routes:
                logger.warning(
                    "[Routes API] request_id=%s no routes returned. response_keys=%s",
                    request_id,
                    list(data.keys()) if isinstance(data, dict) else "not_dict",
                )
                continue
            
            r0 = routes[0]
            encoded = r0.get("polyline", {}).get("encodedPolyline")
            distance_m = r0.get("distanceMeters")
            duration = r0.get("duration")
            
            # duration is like "123s" (ISO 8601 duration format)
            duration_sec = 0.0
            if isinstance(duration, str) and duration.endswith("s"):
                try:
                    duration_sec = float(duration[:-1])
                except ValueError:
                    logger.warning(
                        "[Routes API] request_id=%s invalid duration format: %s",
                        request_id,
                        duration,
                    )
                    duration_sec = 0.0
            elif duration is None:
                logger.debug(
                    "[Routes API] request_id=%s duration field not found in response",
                    request_id,
                )
            
            # 必須フィールドの検証
            if not encoded:
                logger.warning(
                    "[Routes API] request_id=%s route_%d missing encodedPolyline. route_keys=%s",
                    request_id,
                    idx,
                    list(r0.keys()) if isinstance(r0, dict) else "not_dict",
                )
                continue
            
            # Extract elevation and stairway information from steps
            has_stairs = False
            elevation_gain_m = 0.0
            legs = r0.get("legs", [])
            for leg in legs:
                steps = leg.get("steps", [])
                for step in steps:
                    # Check for stairs in navigation instruction
                    nav_instruction = step.get("navigationInstruction", {})
                    if nav_instruction:
                        # Check instructions text
                        instruction_text = nav_instruction.get("instructions", "").lower()
                        if "stairs" in instruction_text or "階段" in instruction_text or "stair" in instruction_text:
                            has_stairs = True
                        
                        # Check maneuver type (if available)
                        maneuver = nav_instruction.get("maneuver", "")
                        if isinstance(maneuver, str):
                            maneuver_lower = maneuver.lower()
                            if "stairs" in maneuver_lower or "階段" in maneuver_lower or "stair" in maneuver_lower:
                                has_stairs = True
                    
                    # Check stepType for elevation changes
                    step_type = step.get("stepType", "")
                    # stepType might indicate elevation changes, but we'll calculate from elevation data if available
            
            # Calculate elevation gain from Elevation API if polyline is available
            if encoded:
                try:
                    elevation_gain_m = await _calculate_elevation_gain(encoded, api_key)
                except Exception as e:
                    logger.warning(f"[Elevation API] Failed to calculate elevation gain: {e}", exc_info=True)
                    elevation_gain_m = 0.0
            
            if encoded and distance_m is not None:
                results.append({
                    "route_id": f"route_{idx}",
                    "polyline": encoded,
                    "distance_km": float(distance_m) / 1000.0,
                    "duration_min": duration_sec / 60.0 if duration_sec else None,
                    "has_stairs": has_stairs,
                    "elevation_gain_m": elevation_gain_m,  # Will be calculated from elevation data if available
                })
        return results
