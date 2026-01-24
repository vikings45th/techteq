from __future__ import annotations

import math
import logging
import random
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


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間の距離（km）を簡易的に計算する"""
    earth_radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = lat2_rad - lat1_rad
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


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

    # 候補を多様化するために方位角を作成（360°を6等分）
    # 毎回少し回転・シャッフルして同条件でも変化させる
    base_headings = [0, 60, 120, 180, -120, -60]
    rotate_deg = random.uniform(-15.0, 15.0)
    headings = [h + rotate_deg for h in base_headings]
    random.shuffle(headings)

    # 片道かつ終了地点が指定されている場合は、その地点を目的地として使用
    end_lat_f = float(end_lat) if end_lat is not None else None
    end_lng_f = float(end_lng) if end_lng is not None else None
    direct_km = None
    if not round_trip and end_lat_f is not None and end_lng_f is not None:
        direct_km = _haversine_km(start_lat, start_lng, end_lat_f, end_lng_f)
        # ほぼ同一地点だとRoutes APIが失敗しやすいので補正
        if direct_km < 0.05:
            logger.warning(
                "[Routes API] request_id=%s end_location too close (%.3fkm). fallback to offsets.",
                request_id,
                direct_km,
            )
            end_lat_f = None
            end_lng_f = None

    if not round_trip and end_lat_f is not None and end_lng_f is not None:
        if direct_km is not None and direct_km < distance_km:
            detour_km = max((distance_km - direct_km) / 2.0, 0.5)
            mid_lat = (start_lat + end_lat_f) / 2.0
            mid_lng = (start_lng + end_lng_f) / 2.0
            dests = [
                {
                    "lat": end_lat_f,
                    "lng": end_lng_f,
                    "waypoints": [_offset_latlng(mid_lat, mid_lng, detour_km, h)],
                }
                for h in headings
            ]
        else:
            dests = [{"lat": end_lat_f, "lng": end_lng_f}]
    else:
        if round_trip:
            # 往復ルート: 形状バリエーションを増やす
            waypoint_distance_km = max(distance_km / 4.0, 0.5)
            radius_km = max(distance_km / (2.0 * math.pi), 0.35)
            max_candidates = 6
            dests = []
            seen = set()

            def add_waypoints(label: str, waypoints: List[Dict[str, float]]) -> None:
                if len(waypoints) < 2:
                    return
                key = tuple((round(wp["lat"], 5), round(wp["lng"], 5)) for wp in waypoints)
                if key in seen:
                    return
                seen.add(key)
                dests.append({"label": label, "waypoints": waypoints})

            # 1) 円に近いループ（四角）を最優先
            if len(dests) < max_candidates:
                for h in headings:
                    angles = [h, h + 90.0, h + 180.0, h + 270.0]
                    waypoints = []
                    for a in angles:
                        r = radius_km * random.uniform(0.9, 1.1)
                        waypoints.append(_offset_latlng(start_lat, start_lng, r, a))
                    add_waypoints("circle_like", waypoints)
                    if len(dests) >= max_candidates:
                        break

            # 2) 三角ループ（従来型）
            if len(dests) < max_candidates:
                for h in headings:
                    if len(dests) >= max_candidates:
                        break
                    dist_scale = random.uniform(0.85, 1.15)
                    distance_km_jitter = waypoint_distance_km * dist_scale
                    angle_shift = random.uniform(35.0, 75.0)
                    p1 = _offset_latlng(start_lat, start_lng, distance_km_jitter, h)
                    p2 = _offset_latlng(start_lat, start_lng, distance_km_jitter, h + angle_shift)
                    p3 = _offset_latlng(start_lat, start_lng, distance_km_jitter, h - angle_shift)
                    add_waypoints("triangle", [p1, p2, p3])

            # 3) 直線的な往復（アウト&バック）
            if len(dests) < max_candidates:
                for h in headings:
                    far_km = waypoint_distance_km * random.uniform(1.4, 1.9)
                    near_km = waypoint_distance_km * random.uniform(0.6, 0.9)
                    p_far = _offset_latlng(start_lat, start_lng, far_km, h)
                    p_near = _offset_latlng(start_lat, start_lng, near_km, h)
                    add_waypoints("out_and_back", [p_far, p_near])
                    if len(dests) >= max_candidates:
                        break

            # 4) 蛇行（ジグザグ）
            if len(dests) < max_candidates:
                for h in headings:
                    base_step_km = max(distance_km / 6.0, 0.4)
                    lateral_km = base_step_km * 0.45
                    waypoints = []
                    for i in range(4):
                        forward_km = base_step_km * (1.0 + i * 0.35)
                        base_pt = _offset_latlng(start_lat, start_lng, forward_km, h)
                        side_heading = h + (90.0 if i % 2 == 0 else -90.0)
                        side_pt = _offset_latlng(base_pt["lat"], base_pt["lng"], lateral_km, side_heading)
                        waypoints.append(side_pt)
                    add_waypoints("serpentine", waypoints)
                    if len(dests) >= max_candidates:
                        break
        else:
            waypoint_distance_km = max(distance_km, 0.5)
            dests = [
                _offset_latlng(
                    start_lat,
                    start_lng,
                    waypoint_distance_km * random.uniform(0.9, 1.1),
                    h,
                )
                for h in headings
            ]
    
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
                # Loop route: start -> (waypoints) -> start
                body["destination"] = {"location": {"latLng": {"latitude": start_lat, "longitude": start_lng}}}
                waypoints = dest.get("waypoints") if isinstance(dest, dict) else dest
                if not waypoints:
                    waypoints = []
                body["intermediates"] = [
                    {"location": {"latLng": {"latitude": wp["lat"], "longitude": wp["lng"]}}}
                    for wp in waypoints
                ]
            else:
                body["destination"] = {"location": {"latLng": {"latitude": dest["lat"], "longitude": dest["lng"]}}}
                if isinstance(dest, dict) and dest.get("waypoints"):
                    body["intermediates"] = [
                        {"location": {"latLng": {"latitude": wp["lat"], "longitude": wp["lng"]}}}
                        for wp in dest["waypoints"]
                    ]
            
            # リクエストのログ出力（デバッグ用）
            if round_trip:
                waypoints = dest.get("waypoints") if isinstance(dest, dict) else dest
                label = dest.get("label", "") if isinstance(dest, dict) else ""
                wp_text = "->".join(
                    [f"({wp['lat']:.6f},{wp['lng']:.6f})" for wp in (waypoints or [])]
                )
                logger.debug(
                    "[Routes API Request] request_id=%s route_%d origin=(%.6f,%.6f) waypoints=%s label=%s round_trip=%s",
                    request_id,
                    idx,
                    start_lat,
                    start_lng,
                    wp_text,
                    label,
                    round_trip,
                )
            else:
                logger.debug(
                    "[Routes API Request] request_id=%s route_%d origin=(%.6f,%.6f) dest=(%.6f,%.6f) waypoints=%d round_trip=%s",
                    request_id,
                    idx,
                    start_lat,
                    start_lng,
                    dest["lat"],
                    dest["lng"],
                    len(dest.get("waypoints") or []) if isinstance(dest, dict) else 0,
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
