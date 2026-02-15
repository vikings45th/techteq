from __future__ import annotations

import json
import logging
import time
import uuid
import random
import math
import asyncio
from typing import Any, Dict, List, Optional, TypedDict

import polyline as polyline_lib
from fastapi import HTTPException
from langgraph.graph import END, StateGraph
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.schemas import (
    FallbackDetail,
    GenerateRouteRequest,
    GenerateRouteResponse,
    LatLng,
    RouteQuality,
    Spot,
    ToolName,
)
from app.services import (
    bq_writer,
    fallback,
    maps_routes_client,
    places_client,
    polyline,
    ranker_client,
    vertex_llm,
)
from app.services.feature_calc import Candidate, calc_features
from app.settings import settings
from app.utils import translate_place_type_to_japanese

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__, "1.0.0")


def _set_span_route_attrs(span: trace.Span, req: GenerateRouteRequest, state: AgentState) -> None:
    if span.is_recording():
        span.set_attribute("route.request_id", req.request_id)
        span.set_attribute("route.theme", req.theme)
        span.set_attribute("route.distance_km", float(req.distance_km))
        span.set_attribute("fallback.used", bool(state.get("fallback_used") or state.get("is_fallback_used", False)))
        fallback_reason = state.get("fallback_reason") or state.get("fallback_reason_str")
        if fallback_reason:
            span.set_attribute("fallback.reason", str(fallback_reason))


class AgentState(TypedDict, total=False):
    request: GenerateRouteRequest
    errors: List[str]
    plan_steps: List[str]
    start_time: float
    tools_used: List[ToolName]
    fallback_reasons: List[str]
    bq_request_logged: bool
    request_row_id: Optional[str]
    candidates: List[Dict[str, Any]]
    routes_api_status: str
    routes_error: Optional[str]
    fallback_used: bool
    fallback_reason: Optional[str]
    candidates_features: List[Dict[str, Any]]
    candidate_features_map: Dict[str, Dict[str, Any]]
    candidate_index_map: Dict[str, int]
    rep_routes_payload: List[Dict[str, Any]]
    scores: List[Dict[str, Any]]
    ranker_status: str
    ranker_error: Optional[str]
    ranker_fallback_used: bool
    score_map: Dict[str, float]
    best_route: Dict[str, Any]
    best_score: Optional[float]
    shown_rank_map: Dict[str, int]
    sample_points: List[tuple[float, float]]
    decoded_points: List[tuple[float, float]]
    places: List[Dict[str, Any]]
    places_status: str
    places_error: Optional[str]
    nav_waypoints: List[LatLng]
    simplify_meta: Dict[str, Any]
    description: str
    desc_llm_status: str
    desc_fallback_used: bool
    summary_type: str
    distance_match: float
    distance_error_km: float
    is_fallback_used: bool
    fallback_reason_str: Optional[str]
    is_fallback_route: bool
    quality_score: float
    total_latency_ms: int
    latency_ms: Dict[str, int]
    fallback_details: List[FallbackDetail]
    title: str
    title_llm_status: str
    title_fallback_used: bool
    response: GenerateRouteResponse


def _init_state(req: GenerateRouteRequest) -> AgentState:
    plan_steps = [
        "validate_request",
        "log_request_bq",
        "generate_candidates_routes",
        "fallback_candidates",
        "compute_features",
        "score_by_ranker",
        "fallback_ranking",
        "select_best_route",
        "sample_points_from_polyline",
        "parallel_postprocess",
        "simplify_polyline_to_waypoints",
        "compute_quality",
        "build_fallback_details",
        "store_candidates_bq",
        "store_proposal_bq",
        "build_response",
    ]
    return {
        "request": req,
        "errors": [],
        "plan_steps": plan_steps,
        "start_time": time.time(),
        "tools_used": [],
        "fallback_reasons": [],
        "bq_request_logged": False,
        "request_row_id": None,
        "candidates": [],
        "routes_api_status": "pending",
        "routes_error": None,
        "fallback_used": False,
        "fallback_reason": None,
        "candidates_features": [],
        "candidate_features_map": {},
        "candidate_index_map": {},
        "rep_routes_payload": [],
        "scores": [],
        "ranker_status": "pending",
        "ranker_error": None,
        "ranker_fallback_used": False,
        "score_map": {},
        "shown_rank_map": {},
        "sample_points": [],
        "decoded_points": [],
        "places": [],
        "places_status": "pending",
        "places_error": None,
        "nav_waypoints": [],
        "simplify_meta": {},
        "desc_llm_status": "pending",
        "desc_fallback_used": False,
        "summary_type": "template",
        "distance_match": 0.0,
        "distance_error_km": 0.0,
        "is_fallback_used": False,
        "fallback_reason_str": None,
        "is_fallback_route": False,
        "quality_score": 0.0,
        "total_latency_ms": 0,
        "latency_ms": {},
        "fallback_details": [],
        "title_llm_status": "pending",
        "title_fallback_used": False,
    }


def _merge_latency(state: AgentState, key: str, elapsed_ms: int) -> Dict[str, int]:
    lat = dict(state.get("latency_ms", {}))
    lat[key] = int(elapsed_ms)
    return lat


def _build_spots_from_places(places: List[Dict[str, Any]]) -> List[Spot]:
    return [
        Spot(
            name=p.get("name", ""),
            type=translate_place_type_to_japanese(p.get("type", "unknown")),
            lat=float(p.get("lat")),
            lng=float(p.get("lng")),
        )
        for p in places
        if p.get("name") and p.get("lat") is not None and p.get("lng") is not None
    ]


def _ensure_tool_used(tools_used: List[ToolName], tool: ToolName) -> List[ToolName]:
    updated = list(tools_used)
    if tool not in updated:
        updated.append(tool)
    return updated


def _select_unique_types(places: List[Dict[str, Any]], max_spots: int) -> List[Dict[str, Any]]:
    if not places:
        return []
    unique_type_spots: List[Dict[str, Any]] = []
    used_types = set()
    for p in places:
        p_type = p.get("type") or "unknown"
        if p_type in used_types:
            continue
        unique_type_spots.append(p)
        used_types.add(p_type)
        if len(unique_type_spots) >= max_spots:
            break

    if len(unique_type_spots) < max_spots:
        for p in places:
            if p in unique_type_spots:
                continue
            unique_type_spots.append(p)
            if len(unique_type_spots) >= max_spots:
                break

    return unique_type_spots[:max_spots]


def _place_dedupe_key(place: Dict[str, Any]) -> tuple[str, str] | None:
    place_id = place.get("place_id")
    if place_id:
        return ("place_id", str(place_id))
    name = place.get("name")
    if name:
        return ("name", str(name))
    lat = place.get("lat")
    lng = place.get("lng")
    if lat is None or lng is None:
        return None
    return ("latlng", f"{float(lat):.5f},{float(lng):.5f}")


def _spot_type_diversity(places: List[Dict[str, Any]]) -> float:
    if not places:
        return 0.0
    types = [
        translate_place_type_to_japanese(p.get("type", "unknown"))
        for p in places
        if p.get("type")
    ]
    if not types:
        return 0.0
    counts: Dict[str, int] = {}
    for t in types:
        counts[t] = counts.get(t, 0) + 1
    max_count = max(counts.values())
    return max(0.0, 1.0 - (max_count / len(types)))


def _filter_places_by_route_distance(
    places: List[Dict[str, Any]],
    decoded_points: List[tuple[float, float]],
    max_distance_m: float,
    max_spots: int,
) -> List[Dict[str, Any]]:
    if not places or not decoded_points:
        return places[:max_spots]

    scored: List[tuple[float, Dict[str, Any]]] = []
    for p in places:
        lat = p.get("lat")
        lng = p.get("lng")
        if lat is None or lng is None:
            continue
        dist_m = polyline.distance_to_path_m(decoded_points, (float(lat), float(lng)))
        if dist_m <= max_distance_m:
            scored.append((dist_m, p))

    scored.sort(key=lambda x: x[0])
    return [p for _, p in scored[:max_spots]]


def _detour_allowance_m(distance_km: float) -> float:
    if distance_km <= 3.0:
        return 150.0
    if distance_km <= 6.0:
        return 250.0
    if distance_km <= 10.0:
        return 400.0
    return 600.0


def _haversine_m(a: LatLng, b: LatLng) -> float:
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = lat2 - lat1
    dlng = math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2.0) ** 2
    return 2.0 * 6371000.0 * math.asin(min(1.0, math.sqrt(h)))


def _ensure_polyline_start(
    decoded_points: List[tuple[float, float]],
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    threshold_m: float = 30.0,
) -> tuple[List[tuple[float, float]], bool]:
    if not decoded_points:
        return decoded_points, False
    start = LatLng(lat=start_lat, lng=start_lng)
    first = LatLng(lat=decoded_points[0][0], lng=decoded_points[0][1])
    changed = False
    if _haversine_m(start, first) > threshold_m:
        decoded_points = [(start_lat, start_lng)] + decoded_points
        changed = True
    if round_trip:
        last = LatLng(lat=decoded_points[-1][0], lng=decoded_points[-1][1])
        if _haversine_m(start, last) > threshold_m:
            decoded_points = decoded_points + [(start_lat, start_lng)]
            changed = True
    return decoded_points, changed


def _dedupe_nearby_points(points: List[LatLng], threshold_m: float = 10.0) -> List[LatLng]:
    if not points:
        return []
    deduped = [points[0]]
    for p in points[1:]:
        if _haversine_m(deduped[-1], p) <= threshold_m:
            continue
        deduped.append(p)
    return deduped


async def _collect_places_two_phase(
    *,
    request_id: str,
    theme: str,
    sample_points: List[tuple[float, float]],
    max_spots: int = 5,
    radius_m: int = 800,
    max_results: int = 3,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    merged: List[Dict[str, Any]] = []
    seen_keys = set()
    hidden_keyword = places_client.pick_hidden_keyword(theme)
    classic_types = places_client.get_classic_place_types_for_theme(theme)
    if settings.PLACES_SAMPLE_POINTS_MAX > 0:
        sample_points = sample_points[: settings.PLACES_SAMPLE_POINTS_MAX]
    phases = [
        {
            "name": "hidden",
            "keyword": hidden_keyword,
            "included_types": None,
            "allow_unfiltered_fallback": False,
        },
        {
            "name": "classic",
            "keyword": None,
            "included_types": classic_types,
            "allow_unfiltered_fallback": True,
        },
    ]

    for phase in phases:
        if len(merged) >= max_spots:
            break
        for (lat, lng) in sample_points:
            if len(merged) >= max_spots:
                break

            logger.debug(
                "[Places] request_id=%s phase=%s searching at (%.6f, %.6f) theme=%s keyword=%s",
                request_id,
                phase["name"],
                lat,
                lng,
                theme,
                phase["keyword"],
            )
            found = await places_client.search_spots(
                lat=float(lat),
                lng=float(lng),
                theme=theme,
                radius_m=radius_m,
                max_results=max_results,
                included_types=phase["included_types"],
                keyword=phase["keyword"],
                allow_unfiltered_fallback=phase["allow_unfiltered_fallback"],
            )
            logger.info(
                "[Places] request_id=%s phase=%s found %d places at (%.6f, %.6f): %s",
                request_id,
                phase["name"],
                len(found),
                lat,
                lng,
                [p.get("name") for p in found],
            )
            for p in found:
                if len(merged) >= max_spots:
                    break

                key = _place_dedupe_key(p)
                if key is None:
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.append(p)

    selected = _select_unique_types(merged, max_spots)
    return merged, selected


async def validate_request(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    errors = list(state["errors"])
    t_start = time.perf_counter()
    if not req.round_trip and req.end_location is None:
        errors.append("end_location is required when round_trip is false")
        raise HTTPException(status_code=422, detail=errors[-1])
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {"errors": errors, "latency_ms": _merge_latency(state, "validate_request", elapsed_ms)}


async def log_request_bq(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    t_start = time.perf_counter()
    try:
        bq_writer.insert_rows(settings.BQ_TABLE_REQUEST, [{
            "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": req.request_id,
            "theme": req.theme,
            "distance_km_target": float(req.distance_km),
            "start_lat": float(req.start_location.lat),
            "start_lng": float(req.start_location.lng),
            "round_trip": bool(req.round_trip),
            "debug": bool(req.debug),
            "client_version": None,
            "user_agent": None,
            "ip_hash": None,
        }])
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        return {
            "bq_request_logged": True,
            "request_row_id": None,
            "latency_ms": _merge_latency(state, "log_request_bq", elapsed_ms),
        }
    except Exception as e:
        logger.warning("[BQ Request Log Failed] request_id=%s err=%r", req.request_id, e)
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        return {
            "bq_request_logged": False,
            "request_row_id": None,
            "latency_ms": _merge_latency(state, "log_request_bq", elapsed_ms),
        }


async def generate_candidates_routes(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    tools_used = list(state["tools_used"])
    candidates: List[Dict[str, Any]] = []
    status = "error"
    error: Optional[str] = None
    t_start = time.perf_counter()
    with _tracer.start_as_current_span("step.generate_candidates") as span:
        _set_span_route_attrs(span, req, state)
        try:
            effective_end_location = None if req.round_trip else req.end_location
            max_routes = max(1, int(settings.MAX_ROUTES))
            min_routes = max(1, int(settings.MIN_ROUTES))
            max_error_ratio = float(settings.ROUTE_DISTANCE_ERROR_RATIO_MAX)
            max_attempts = max(1, int(settings.ROUTE_DISTANCE_RETRY_MAX) + 1)
            target_distance_km = float(req.distance_km)
            original_target_km = target_distance_km
            short_max_km = float(getattr(settings, "SHORT_DISTANCE_MAX_KM", 2.0))
            short_ratio = float(getattr(settings, "SHORT_DISTANCE_TARGET_RATIO", 0.9))
            if original_target_km <= short_max_km:
                max_error_ratio = min(max_error_ratio, 0.2)
            if target_distance_km <= short_max_km and 0.5 <= short_ratio < 1.0:
                adjusted = max(0.5, target_distance_km * short_ratio)
                if adjusted != target_distance_km:
                    logger.info(
                        "[Routes Target PreAdjust] request_id=%s target=%.3f adjusted=%.3f ratio=%.2f",
                        req.request_id,
                        target_distance_km,
                        adjusted,
                        short_ratio,
                    )
                    target_distance_km = adjusted

            for attempt in range(1, max_attempts + 1):
                attempt_candidates: List[Dict[str, Any]] = []
                best_score: Optional[float] = None
                filtered_out = 0
                closest_distance_km: Optional[float] = None
                closest_error_ratio: Optional[float] = None

                dests = maps_routes_client.compute_route_dests(
                    request_id=req.request_id,
                    start_lat=float(req.start_location.lat),
                    start_lng=float(req.start_location.lng),
                    end_lat=float(effective_end_location.lat) if effective_end_location else None,
                    end_lng=float(effective_end_location.lng) if effective_end_location else None,
                    distance_km=target_distance_km,
                    round_trip=bool(req.round_trip),
                )
                dests = dests[:max_routes]

                t0 = time.perf_counter()
                with _tracer.start_as_current_span("step.call_maps_routes") as maps_span:
                    _set_span_route_attrs(maps_span, req, state)
                    for idx, dest in enumerate(dests, start=1):
                        route = await maps_routes_client.compute_route_candidate(
                            request_id=req.request_id,
                            start_lat=float(req.start_location.lat),
                            start_lng=float(req.start_location.lng),
                            dest=dest,
                            idx=idx,
                            round_trip=bool(req.round_trip),
                        )
                        if not route:
                            continue

                        # ルートの妥当性チェック
                        route_distance_km = float(route.get("distance_km") or 0.0)
                        route_polyline = route.get("polyline", "").strip()

                        # 距離が0以下、または極端に小さい値（0.01km = 10m以下）の場合は無効
                        if route_distance_km <= 0.01:
                            filtered_out += 1
                            logger.warning(
                                "[Routes Invalid] request_id=%s idx=%d distance too small: %.3fkm",
                                req.request_id,
                                idx,
                                route_distance_km,
                            )
                            continue

                        # polylineが空、または無効な値の場合は無効
                        if not route_polyline or route_polyline in ("", "xxxx", "~oia@"):
                            filtered_out += 1
                            logger.warning(
                                "[Routes Invalid] request_id=%s idx=%d invalid polyline: %s",
                                req.request_id,
                                idx,
                                route_polyline[:20] if route_polyline else "empty",
                            )
                            continue

                        if target_distance_km > 0 and max_error_ratio >= 0:
                            error_base_km = original_target_km if original_target_km > 0 else target_distance_km
                            distance_error_ratio = abs(route_distance_km - error_base_km) / error_base_km
                            if closest_error_ratio is None or distance_error_ratio < closest_error_ratio:
                                closest_error_ratio = distance_error_ratio
                                closest_distance_km = route_distance_km
                            if distance_error_ratio > max_error_ratio:
                                filtered_out += 1
                                logger.info(
                                    "[Routes Filtered] request_id=%s idx=%d error_ratio=%.3f target=%.3f actual=%.3f threshold=%.3f attempt=%d/%d",
                                    req.request_id,
                                    idx,
                                    distance_error_ratio,
                                    target_distance_km,
                                    route_distance_km,
                                    max_error_ratio,
                                    attempt,
                                    max_attempts,
                                )
                                continue
                        attempt_candidates.append(route)
                        score = _heuristic_score({"distance_km": route.get("distance_km")}, req)
                        if best_score is None or score > best_score:
                            best_score = score
                        if len(attempt_candidates) >= min_routes and best_score >= float(settings.SCORE_THRESHOLD):
                            logger.info(
                                "[Routes Early Exit] request_id=%s candidates=%d best_score=%.3f threshold=%.3f",
                                req.request_id,
                                len(attempt_candidates),
                                best_score,
                                float(settings.SCORE_THRESHOLD),
                            )
                            break
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(
                    "[Routes Latency] request_id=%s candidates=%d elapsed_ms=%d attempt=%d/%d",
                    req.request_id,
                    len(attempt_candidates),
                    elapsed_ms,
                    attempt,
                    max_attempts,
                )

                if attempt_candidates:
                    candidates = attempt_candidates
                    break

                if attempt < max_attempts:
                    if original_target_km <= short_max_km and closest_distance_km and closest_distance_km > 0:
                        adjusted = (target_distance_km * target_distance_km) / closest_distance_km
                        adjusted = max(0.5, min(original_target_km, adjusted))
                        if adjusted != target_distance_km:
                            logger.info(
                                "[Routes Target Adjust] request_id=%s target=%.3f adjusted=%.3f observed=%.3f attempt=%d/%d",
                                req.request_id,
                                target_distance_km,
                                adjusted,
                                closest_distance_km,
                                attempt,
                                max_attempts,
                            )
                            target_distance_km = adjusted
                    logger.info(
                        "[Routes Retry] request_id=%s filtered_out=%d attempt=%d/%d",
                        req.request_id,
                        filtered_out,
                        attempt,
                        max_attempts,
                    )

            if candidates:
                tools_used = _ensure_tool_used(tools_used, "maps_routes")
                status = "ok"
            else:
                status = "empty"
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            error = repr(e)
            logger.warning("[Maps Routes Failed] request_id=%s err=%r", req.request_id, e)
        if span.is_recording():
            span.set_attribute("fallback.used", status != "ok")
            if error:
                span.set_attribute("fallback.reason", error)

    elapsed_total_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "candidates": candidates,
        "routes_api_status": status,
        "routes_error": error,
        "tools_used": tools_used,
        "latency_ms": _merge_latency(state, "generate_candidates_routes", elapsed_total_ms),
    }


async def fallback_candidates(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    fallback_reasons = list(state["fallback_reasons"])
    t_start = time.perf_counter()
    start_lat = float(req.start_location.lat)
    start_lng = float(req.start_location.lng)
    effective_end_location = None if req.round_trip else req.end_location

    if effective_end_location is not None:
        fallback_points = [
            (start_lat, start_lng),
            (float(effective_end_location.lat), float(effective_end_location.lng)),
        ]
    else:
        fallback_points = [
            (start_lat, start_lng),
            (start_lat + 0.0001, start_lng + 0.0001),
        ]

    safe_polyline = ""
    try:
        safe_polyline = polyline_lib.encode(fallback_points)
    except Exception as e:
        logger.warning("[Fallback Polyline Error] request_id=%s err=%r", req.request_id, e)
        try:
            safe_polyline = polyline_lib.encode([
                (start_lat, start_lng),
                (start_lat + 0.001, start_lng + 0.001),
            ])
        except Exception:
            safe_polyline = "~oia@"

    if not safe_polyline or safe_polyline.strip() == "":
        safe_polyline = "~oia@"

    candidates = [{
        "route_id": "fallback_dummy",
        "polyline": safe_polyline,
        "distance_km": float(req.distance_km),
        "duration_min": 32.0,
        "theme": req.theme,
        "is_fallback": True,
    }]
    fallback_reasons.append("maps_routes_failed")
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "candidates": candidates,
        "fallback_used": True,
        "fallback_reason": "maps_routes_failed",
        "fallback_reasons": fallback_reasons,
        "latency_ms": _merge_latency(state, "fallback_candidates", elapsed_ms),
    }


async def compute_features(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    candidates = state["candidates"]
    rep_routes_payload: List[Dict[str, Any]] = []
    candidate_features_map: Dict[str, Dict[str, Any]] = {}
    candidate_features_list: List[Dict[str, Any]] = []
    candidate_index_map: Dict[str, int] = {}
    normalized_candidates: List[Dict[str, Any]] = []
    t_start = time.perf_counter()

    for i, c in enumerate(candidates, start=1):
        normalized = dict(c)
        normalized["route_id"] = str(uuid.uuid4())
        normalized.setdefault("is_fallback", False)
        normalized.setdefault("theme", req.theme)
        cand = Candidate(
            route_id=normalized["route_id"],
            polyline=normalized.get("polyline", "xxxx"),
            distance_km=float(normalized.get("distance_km", req.distance_km)),
            duration_min=float(normalized.get("duration_min") or 30.0 + i),
            loop_closure_m=20.0,
            bbox_area=0.5,
            path_length_ratio=1.3,
            turn_count=10 + i,
            has_stairs=normalized.get("has_stairs", False),
            elevation_gain_m=float(normalized.get("elevation_gain_m", 0.0)),
        )
        spot_type_diversity = 0.0
        detour_over_ratio = 0.0
        detour_allowance_m = _detour_allowance_m(float(req.distance_km))
        try:
            decoded_points: List[tuple[float, float]] = []
            if cand.polyline and cand.polyline.strip() not in ("", "xxxx"):
                decoded_points = polyline.decode_polyline(cand.polyline)
            sample_points = polyline.sample_points(decoded_points, [0.25, 0.5, 0.75]) if decoded_points else []
            if not sample_points:
                sample_points = [(float(req.start_location.lat), float(req.start_location.lng))]
            merged_places, _ = await _collect_places_two_phase(
                request_id=req.request_id,
                theme=req.theme,
                sample_points=sample_points,
                max_spots=5,
                radius_m=settings.PLACES_RADIUS_M,
                max_results=settings.PLACES_MAX_RESULTS,
            )
            spot_type_diversity = _spot_type_diversity(merged_places)
            if decoded_points and merged_places:
                over_ratios: List[float] = []
                for p in merged_places:
                    lat = p.get("lat")
                    lng = p.get("lng")
                    if lat is None or lng is None:
                        continue
                    detour_m = polyline.distance_to_path_m(decoded_points, (float(lat), float(lng)))
                    if detour_allowance_m <= 0:
                        continue
                    over = max(0.0, detour_m - detour_allowance_m)
                    over_ratios.append(over / detour_allowance_m)
                if over_ratios:
                    detour_over_ratio = sum(over_ratios) / len(over_ratios)
        except Exception as e:
            logger.warning(
                "[Places Diversity Failed] request_id=%s route_id=%s err=%r",
                req.request_id,
                cand.route_id,
                e,
            )
        feats = calc_features(
            candidate=cand,
            theme=req.theme,
            round_trip_req=req.round_trip,
            distance_km_target=float(req.distance_km),
            relaxation_step=0,
            candidate_rank_in_theme=i,
            spot_type_diversity=spot_type_diversity,
            detour_over_ratio=detour_over_ratio,
            detour_allowance_m=detour_allowance_m,
        )
        candidate_features_map[cand.route_id] = feats
        candidate_index_map[cand.route_id] = i
        candidate_features_list.append({"route_id": cand.route_id, "features": feats})
        if i <= 5:
            rep_routes_payload.append({"route_id": cand.route_id, "features": feats})
        normalized_candidates.append(normalized)

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "candidates": normalized_candidates,
        "rep_routes_payload": rep_routes_payload,
        "candidate_features_map": candidate_features_map,
        "candidate_index_map": candidate_index_map,
        "candidates_features": candidate_features_list,
        "latency_ms": _merge_latency(state, "compute_features", elapsed_ms),
    }


async def score_by_ranker(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    tools_used = list(state["tools_used"])
    fallback_reasons = list(state["fallback_reasons"])
    rep_routes_payload = state["rep_routes_payload"]
    scores: List[Dict[str, Any]] = []
    status = "error"
    error: Optional[str] = None
    score_map: Dict[str, float] = {}
    t_start = time.perf_counter()

    with _tracer.start_as_current_span("step.call_ranker") as span:
        _set_span_route_attrs(span, req, state)
        try:
            t0 = time.perf_counter()
            scores_list, _failed_ids = await ranker_client.rank_routes(req.request_id, rep_routes_payload)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "[Ranker Latency] request_id=%s routes=%d elapsed_ms=%d",
                req.request_id,
                len(rep_routes_payload),
                elapsed_ms,
            )
            for item in scores_list:
                if "route_id" in item and "score" in item:
                    score_map[item["route_id"]] = float(item["score"])
            scores = [{"route_id": rid, "score": score} for rid, score in score_map.items()]
            if score_map:
                tools_used = _ensure_tool_used(tools_used, "ranker")
                status = "ok"
            else:
                status = "empty"
                fallback_reasons.append("ranker_failed")
                logger.warning("[Ranker Empty] request_id=%s no scores returned", req.request_id)
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            error = repr(e)
            fallback_reasons.append("ranker_failed")
            logger.error("[Ranker Error] request_id=%s err=%r", req.request_id, e)
        if span.is_recording():
            span.set_attribute("fallback.used", status != "ok")
            if error:
                span.set_attribute("fallback.reason", error)

    elapsed_total_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "scores": scores,
        "score_map": score_map,
        "ranker_status": status,
        "ranker_error": error,
        "tools_used": tools_used,
        "fallback_reasons": fallback_reasons,
        "latency_ms": _merge_latency(state, "score_by_ranker", elapsed_total_ms),
    }


def _heuristic_score(features: Dict[str, Any], req: GenerateRouteRequest) -> float:
    distance_error_ratio = features.get("distance_error_ratio")
    if distance_error_ratio is None:
        distance_km = features.get("distance_km", float(req.distance_km))
        target = float(req.distance_km)
        distance_error_ratio = abs(distance_km - target) / target if target > 0 else 1.0
    turn_count = float(features.get("turn_count") or 0.0)
    elevation_gain = float(features.get("elevation_gain_m") or 0.0)
    score = 1.0 - min(distance_error_ratio, 1.0)
    score += 0.1 / (1.0 + turn_count)
    score += 0.05 / (1.0 + elevation_gain)
    return max(0.0, score)


async def fallback_ranking(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    fallback_reasons = list(state["fallback_reasons"])
    scores: List[Dict[str, Any]] = []
    score_map: Dict[str, float] = {}
    t_start = time.perf_counter()

    for c in state["candidates"]:
        route_id = c.get("route_id")
        feats = state["candidate_features_map"].get(route_id, {})
        score = _heuristic_score(feats, req)
        score_map[route_id] = float(score)
        scores.append({"route_id": route_id, "score": float(score)})

    if "ranker_failed" not in fallback_reasons:
        fallback_reasons.append("ranker_failed")

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "scores": scores,
        "score_map": score_map,
        "ranker_status": "fallback",
        "ranker_fallback_used": True,
        "fallback_reasons": fallback_reasons,
        "latency_ms": _merge_latency(state, "fallback_ranking", elapsed_ms),
    }


async def select_best_route(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    candidates = state["candidates"]
    score_map = state["score_map"]
    fallback_reasons = list(state.get("fallback_reasons", []))
    t_start = time.perf_counter()
    best_route = fallback.choose_best_route(candidates, score_map, req.theme)
    if best_route is None:
        raise HTTPException(status_code=422, detail="No viable route found")

    # 選択されたルートの妥当性を最終チェック
    route_distance_km = float(best_route.get("distance_km") or 0.0)
    route_polyline = best_route.get("polyline", "").strip()
    
    # 距離が0以下、または極端に小さい値（0.01km = 10m以下）の場合は無効
    if route_distance_km <= 0.01:
        logger.error(
            "[Select Best Route Invalid] request_id=%s route_id=%s distance too small: %.3fkm. Using fallback.",
            req.request_id,
            best_route.get("route_id"),
            route_distance_km,
        )
        # フォールバックルートを生成
        start_lat = float(req.start_location.lat)
        start_lng = float(req.start_location.lng)
        effective_end_location = None if req.round_trip else req.end_location
        
        if effective_end_location is not None:
            fallback_points = [
                (start_lat, start_lng),
                (float(effective_end_location.lat), float(effective_end_location.lng)),
            ]
        else:
            fallback_points = [
                (start_lat, start_lng),
                (start_lat + 0.0001, start_lng + 0.0001),
            ]
        
        safe_polyline = ""
        try:
            safe_polyline = polyline_lib.encode(fallback_points)
        except Exception:
            safe_polyline = "~oia@"
        
        if not safe_polyline or safe_polyline.strip() == "":
            safe_polyline = "~oia@"
        
        best_route = {
            "route_id": "fallback_dummy",
            "polyline": safe_polyline,
            "distance_km": float(req.distance_km),
            "duration_min": 32.0,
            "theme": req.theme,
            "is_fallback": True,
        }
        if "invalid_route_detected" not in fallback_reasons:
            fallback_reasons.append("invalid_route_detected")
    
    # polylineが空、または無効な値の場合は無効
    elif not route_polyline or route_polyline in ("", "xxxx", "~oia@"):
        logger.error(
            "[Select Best Route Invalid] request_id=%s route_id=%s invalid polyline: %s. Using fallback.",
            req.request_id,
            best_route.get("route_id"),
            route_polyline[:20] if route_polyline else "empty",
        )
        # フォールバックルートを生成
        start_lat = float(req.start_location.lat)
        start_lng = float(req.start_location.lng)
        effective_end_location = None if req.round_trip else req.end_location
        
        if effective_end_location is not None:
            fallback_points = [
                (start_lat, start_lng),
                (float(effective_end_location.lat), float(effective_end_location.lng)),
            ]
        else:
            fallback_points = [
                (start_lat, start_lng),
                (start_lat + 0.0001, start_lng + 0.0001),
            ]
        
        safe_polyline = ""
        try:
            safe_polyline = polyline_lib.encode(fallback_points)
        except Exception:
            safe_polyline = "~oia@"
        
        if not safe_polyline or safe_polyline.strip() == "":
            safe_polyline = "~oia@"
        
        best_route = {
            "route_id": "fallback_dummy",
            "polyline": safe_polyline,
            "distance_km": float(req.distance_km),
            "duration_min": 32.0,
            "theme": req.theme,
            "is_fallback": True,
        }
        if "invalid_route_detected" not in fallback_reasons:
            fallback_reasons.append("invalid_route_detected")

    shown_rank_map: Dict[str, int] = {}
    if score_map:
        for rank, (route_id, _score) in enumerate(
            sorted(score_map.items(), key=lambda x: x[1], reverse=True),
            start=1,
        ):
            shown_rank_map[route_id] = rank

    best_score = score_map.get(best_route.get("route_id"))

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "best_route": best_route,
        "best_score": best_score,
        "shown_rank_map": shown_rank_map,
        "fallback_reasons": fallback_reasons,
        "latency_ms": _merge_latency(state, "select_best_route", elapsed_ms),
    }


async def sample_points_from_polyline(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    best_route = state["best_route"]
    encoded = (best_route.get("polyline") or "").strip()
    decoded_points: List[tuple[float, float]] = []
    sample_points: List[tuple[float, float]] = []
    updated_route = dict(best_route)
    t_start = time.perf_counter()

    try:
        if encoded and encoded != "xxxx":
            decoded_points = polyline.decode_polyline(encoded)
            decoded_points, changed = _ensure_polyline_start(
                decoded_points=decoded_points,
                start_lat=float(req.start_location.lat),
                start_lng=float(req.start_location.lng),
                round_trip=bool(req.round_trip),
            )
            if changed:
                updated_route["polyline"] = polyline_lib.encode(decoded_points)
            sample_points = polyline.sample_points(decoded_points, [0.25, 0.5, 0.75])
    except Exception as e:
        logger.warning("[Polyline Decode Failed] request_id=%s err=%r", req.request_id, e)

    if not sample_points:
        sample_points = [(float(req.start_location.lat), float(req.start_location.lng))]

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "sample_points": sample_points,
        "decoded_points": decoded_points,
        "best_route": updated_route,
        "latency_ms": _merge_latency(state, "sample_points_from_polyline", elapsed_ms),
    }


async def fetch_places(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    tools_used = list(state["tools_used"])
    sample_points = state["sample_points"]
    decoded_points = state.get("decoded_points") or []
    status = "error"
    error: Optional[str] = None
    places: List[Dict[str, Any]] = []
    t_start = time.perf_counter()

    with _tracer.start_as_current_span("step.call_places") as span:
        _set_span_route_attrs(span, req, state)
        try:
            t0 = time.perf_counter()
            merged, selected = await _collect_places_two_phase(
                request_id=req.request_id,
                theme=req.theme,
                sample_points=sample_points,
                max_spots=5,
                radius_m=settings.PLACES_RADIUS_M,
                max_results=settings.PLACES_MAX_RESULTS,
            )
            places = selected
            if decoded_points:
                filtered = _filter_places_by_route_distance(
                    places=places,
                    decoded_points=decoded_points,
                    max_distance_m=float(settings.SPOT_MAX_DISTANCE_M),
                    max_spots=5,
                )
                if len(filtered) < 3:
                    filtered = _filter_places_by_route_distance(
                        places=merged,
                        decoded_points=decoded_points,
                        max_distance_m=float(settings.SPOT_MAX_DISTANCE_M_RELAXED),
                        max_spots=5,
                    )
                if len(filtered) < 3:
                    filtered = _filter_places_by_route_distance(
                        places=merged,
                        decoded_points=decoded_points,
                        max_distance_m=float(settings.SPOT_MAX_DISTANCE_M_FALLBACK),
                        max_spots=5,
                    )
                places = filtered
            if places:
                tools_used = _ensure_tool_used(tools_used, "places")
                status = "ok"
            else:
                status = "empty"
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "[Places Latency] request_id=%s spots=%d elapsed_ms=%d",
                req.request_id,
                len(places),
                elapsed_ms,
            )
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            error = repr(e)
            logger.error("[Places Error] request_id=%s err=%r", req.request_id, e)
        if span.is_recording():
            span.set_attribute("fallback.used", status != "ok")
            if error:
                span.set_attribute("fallback.reason", error)

    elapsed_total_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "places": places,
        "places_status": status,
        "places_error": error,
        "tools_used": tools_used,
        "latency_ms": _merge_latency(state, "fetch_places", elapsed_total_ms),
    }


async def parallel_postprocess(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    tools_used = list(state["tools_used"])
    fallback_reasons = list(state["fallback_reasons"])
    sem = asyncio.Semaphore(int(settings.CONCURRENCY))

    async def _run_with_sem(coro):
        async with sem:
            return await coro

    state_for_vertex = dict(state)
    state_for_vertex["places"] = []

    t0 = time.perf_counter()
    tasks = {
        "places": asyncio.create_task(_run_with_sem(fetch_places(state))),
        "text": asyncio.create_task(_run_with_sem(generate_title_description_vertex(state_for_vertex))),
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("[Postprocess Latency] request_id=%s elapsed_ms=%d", req.request_id, elapsed_ms)

    result_map = dict(zip(tasks.keys(), results))
    places_result: Dict[str, Any] = {}
    text_result: Dict[str, Any] = {}

    if isinstance(result_map.get("places"), Exception):
        logger.error("[Places Parallel Error] request_id=%s err=%r", req.request_id, result_map["places"])
        places_result = {
            "places": [],
            "places_status": "error",
            "places_error": repr(result_map["places"]),
            "tools_used": tools_used,
        }
    else:
        places_result = result_map.get("places") or {}

    if isinstance(result_map.get("text"), Exception):
        logger.error("[Text Parallel Error] request_id=%s err=%r", req.request_id, result_map["text"])
        template_candidates = [
            "少しずつ、歩いてみませんか。優しい散歩ルートです。",
            "無理せず、自分のペースで歩ける散歩ルートです。",
            "外に出てみることで、少し気持ちが変わるかもしれません。",
        ]
        text_result = {
            "description": random.choice(template_candidates),
            "title": vertex_llm.fallback_title(
                theme=req.theme,
                distance_km=float(state["best_route"].get("distance_km", req.distance_km)),
                duration_min=float(state["best_route"].get("duration_min") or 30.0),
                spots=[],
            ),
            "desc_llm_status": "error",
            "desc_fallback_used": True,
            "summary_type": "template",
            "title_llm_status": "error",
            "title_fallback_used": True,
            "tools_used": tools_used,
            "fallback_reasons": fallback_reasons + ["vertex_llm_failed"],
        }
    else:
        text_result = result_map.get("text") or {}

    if places_result.get("tools_used"):
        tools_used = places_result["tools_used"]
    if text_result.get("tools_used"):
        tools_used = text_result["tools_used"]
    if text_result.get("fallback_reasons"):
        fallback_reasons = text_result["fallback_reasons"]

    latency_ms = _merge_latency(state, "parallel_postprocess", elapsed_ms)
    if places_result.get("latency_ms"):
        latency_ms.update(places_result["latency_ms"])
    if text_result.get("latency_ms"):
        latency_ms.update(text_result["latency_ms"])

    return {
        "places": places_result.get("places", []),
        "places_status": places_result.get("places_status", "error"),
        "places_error": places_result.get("places_error"),
        "description": text_result.get("description"),
        "desc_llm_status": text_result.get("desc_llm_status"),
        "desc_fallback_used": text_result.get("desc_fallback_used"),
        "summary_type": text_result.get("summary_type"),
        "title": text_result.get("title"),
        "title_llm_status": text_result.get("title_llm_status"),
        "title_fallback_used": text_result.get("title_fallback_used"),
        "tools_used": tools_used,
        "fallback_reasons": fallback_reasons,
        "latency_ms": latency_ms,
    }


async def simplify_polyline_to_waypoints(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    decoded_points = state["decoded_points"]
    sample_points = state["sample_points"]
    places = state.get("places", [])
    simplify_meta: Dict[str, Any] = {}
    t_start = time.perf_counter()

    if decoded_points:
        simplified = polyline.simplify_douglas_peucker(decoded_points, epsilon_m=20.0)
        waypoint_points = polyline.pick_waypoints(simplified, max_points=10)
        simplify_meta = {
            "points_before": len(decoded_points),
            "points_after": len(simplified),
            "reduction_ratio": (len(simplified) / len(decoded_points)) if decoded_points else 0.0,
        }
    else:
        waypoint_points = sample_points[:10] if sample_points else []
        simplify_meta = {
            "points_before": 0,
            "points_after": len(waypoint_points),
            "reduction_ratio": 0.0,
        }

    nav_waypoints = [LatLng(lat=float(lat), lng=float(lng)) for (lat, lng) in waypoint_points]
    combined = nav_waypoints
    seen = set()
    deduped: List[LatLng] = []
    for wp in combined:
        key = (round(wp.lat, 6), round(wp.lng, 6))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(wp)

    max_points = 10
    if len(deduped) > max_points:
        trimmed: List[LatLng] = []
        # ルートの始点・終点を優先的に入れる
        if len(nav_waypoints) >= 2:
            for candidate in (nav_waypoints[0], nav_waypoints[-1]):
                if len(trimmed) >= max_points:
                    break
                if candidate in trimmed:
                    continue
                trimmed.append(candidate)
        for wp in deduped:
            if len(trimmed) >= max_points:
                break
            if wp in trimmed:
                continue
            trimmed.append(wp)
        deduped = trimmed[:max_points]

    nav_waypoints = deduped
    start_wp = LatLng(lat=float(req.start_location.lat), lng=float(req.start_location.lng))
    start_key = (round(start_wp.lat, 6), round(start_wp.lng, 6))
    nav_waypoints = [wp for wp in nav_waypoints if (round(wp.lat, 6), round(wp.lng, 6)) != start_key]
    nav_waypoints.insert(0, start_wp)
    if len(nav_waypoints) > max_points:
        nav_waypoints = nav_waypoints[:max_points]
    nav_waypoints = _dedupe_nearby_points(nav_waypoints, threshold_m=10.0)
    if req.round_trip and nav_waypoints:
        first = nav_waypoints[0]
        last = nav_waypoints[-1]
        if _haversine_m(first, last) > 10.0:
            if len(nav_waypoints) < max_points:
                nav_waypoints.append(first)
            else:
                nav_waypoints[-1] = first
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "nav_waypoints": nav_waypoints,
        "simplify_meta": simplify_meta,
        "latency_ms": _merge_latency(state, "simplify_polyline_to_waypoints", elapsed_ms),
    }


async def generate_description_vertex(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    best_route = state["best_route"]
    tools_used = list(state["tools_used"])
    fallback_reasons = list(state["fallback_reasons"])
    spots = _build_spots_from_places(state["places"])

    spots_names = [s.name for s in spots] if spots else []
    spots_text = f"（見どころ: {', '.join(spots_names)}）" if spots_names else ""
    template_candidates = [
        f"少しずつ、歩いてみませんか。優しい散歩ルートです{spots_text}",
        f"無理せず、自分のペースで歩ける散歩ルートです{spots_text}",
        f"外に出てみることで、少し気持ちが変わるかもしれません{spots_text}",
    ]
    description = random.choice(template_candidates)
    status = "pending"
    fallback_used = True
    summary_type = "template"

    try:
        t0 = time.perf_counter()
        vertex_summary = await vertex_llm.generate_summary(
            theme=req.theme,
            distance_km=float(best_route.get("distance_km", req.distance_km)),
            duration_min=float(best_route.get("duration_min") or 30.0),
            spots=spots,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[Vertex Summary Latency] request_id=%s elapsed_ms=%d",
            req.request_id,
            elapsed_ms,
        )
        if vertex_summary:
            description = vertex_summary
            status = "ok"
            fallback_used = False
            summary_type = "vertex_llm"
            tools_used = _ensure_tool_used(tools_used, "vertex_llm")
        else:
            status = "empty"
            fallback_reasons.append("vertex_llm_failed")
            logger.warning("[Vertex LLM Empty] request_id=%s (returned empty)", req.request_id)
    except Exception as e:
        status = "error"
        fallback_reasons.append("vertex_llm_failed")
        logger.error("[Vertex LLM Error] request_id=%s err=%r", req.request_id, e)

    return {
        "description": description,
        "desc_llm_status": status,
        "desc_fallback_used": fallback_used,
        "summary_type": summary_type,
        "tools_used": tools_used,
        "fallback_reasons": fallback_reasons,
    }


async def generate_title_description_vertex(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    best_route = state["best_route"]
    tools_used = list(state["tools_used"])
    fallback_reasons = list(state["fallback_reasons"])
    spots = _build_spots_from_places(state["places"])

    spots_names = [s.name for s in spots] if spots else []
    spots_text = f"（見どころ: {', '.join(spots_names)}）" if spots_names else ""
    template_candidates = [
        f"少しずつ、歩いてみませんか。優しい散歩ルートです{spots_text}",
        f"無理せず、自分のペースで歩ける散歩ルートです{spots_text}",
        f"外に出てみることで、少し気持ちが変わるかもしれません{spots_text}",
    ]
    description = random.choice(template_candidates)
    title = vertex_llm.fallback_title(
        theme=req.theme,
        distance_km=float(best_route.get("distance_km", req.distance_km)),
        duration_min=float(best_route.get("duration_min") or 30.0),
        spots=spots,
    )
    desc_status = "pending"
    title_status = "pending"
    desc_fallback_used = True
    title_fallback_used = True
    summary_type = "template"

    elapsed_ms = 0
    try:
        t0 = time.perf_counter()
        result = await vertex_llm.generate_title_and_description(
            theme=req.theme,
            distance_km=float(best_route.get("distance_km", req.distance_km)),
            duration_min=float(best_route.get("duration_min") or 30.0),
            spots=spots,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[Vertex Title+Summary Latency] request_id=%s elapsed_ms=%d",
            req.request_id,
            elapsed_ms,
        )
        if result:
            title = result.get("title") or title
            description = result.get("description") or description
            desc_status = "ok"
            title_status = "ok"
            desc_fallback_used = False
            title_fallback_used = False
            summary_type = "vertex_llm"
            tools_used = _ensure_tool_used(tools_used, "vertex_llm")
        else:
            desc_status = "empty"
            title_status = "empty"
            fallback_reasons.append("vertex_llm_failed")
            logger.warning("[Vertex LLM Empty] request_id=%s (returned empty)", req.request_id)
    except Exception as e:
        desc_status = "error"
        title_status = "error"
        fallback_reasons.append("vertex_llm_failed")
        logger.error("[Vertex LLM Error] request_id=%s err=%r", req.request_id, e)

    return {
        "title": title,
        "description": description,
        "desc_llm_status": desc_status,
        "desc_fallback_used": desc_fallback_used,
        "summary_type": summary_type,
        "title_llm_status": title_status,
        "title_fallback_used": title_fallback_used,
        "tools_used": tools_used,
        "fallback_reasons": fallback_reasons,
        "latency_ms": _merge_latency(state, "vertex_title_description", elapsed_ms),
    }


async def generate_title_vertex(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    best_route = state["best_route"]
    tools_used = list(state["tools_used"])
    spots = _build_spots_from_places(state["places"])

    title = vertex_llm.fallback_title(
        theme=req.theme,
        distance_km=float(best_route.get("distance_km", req.distance_km)),
        duration_min=float(best_route.get("duration_min") or 30.0),
        spots=spots,
    )
    status = "fallback"
    fallback_used = True

    try:
        t0 = time.perf_counter()
        vertex_title = await vertex_llm.generate_title(
            theme=req.theme,
            distance_km=float(best_route.get("distance_km", req.distance_km)),
            duration_min=float(best_route.get("duration_min") or 30.0),
            spots=spots,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[Vertex Title Latency] request_id=%s elapsed_ms=%d",
            req.request_id,
            elapsed_ms,
        )
        if vertex_title:
            title = vertex_title
            status = "ok"
            fallback_used = False
            tools_used = _ensure_tool_used(tools_used, "vertex_llm")
        else:
            status = "empty"
    except Exception as e:
        status = "error"
        logger.warning("[Vertex LLM Title Error] request_id=%s err=%r", req.request_id, e)

    return {
        "title": title,
        "title_llm_status": status,
        "title_fallback_used": fallback_used,
        "tools_used": tools_used,
    }


async def compute_quality(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    best_route = state["best_route"]
    tools_used = state["tools_used"]
    fallback_reasons = state["fallback_reasons"]
    t_start = time.perf_counter()

    target_distance_km = float(req.distance_km)
    actual_distance_km = float(best_route.get("distance_km", target_distance_km))
    distance_error_km = abs(actual_distance_km - target_distance_km)

    distance_error_ratio = distance_error_km / target_distance_km if target_distance_km > 0 else 1.0
    if distance_error_ratio <= 0.1:
        distance_match = 1.0
    elif distance_error_ratio >= 0.5:
        distance_match = 0.0
    else:
        distance_match = 1.0 - ((distance_error_ratio - 0.1) / 0.4)

    is_fallback_used = len(fallback_reasons) > 0 or state.get("fallback_used", False)
    fallback_reason_str = ",".join(fallback_reasons) if fallback_reasons else None
    is_fallback_route = bool(best_route.get("is_fallback")) or is_fallback_used

    quality_score = 0.0
    if not is_fallback_route:
        quality_score += 0.3
    quality_score += distance_match * 0.4
    if len(tools_used) >= 3:
        quality_score += 0.3
    quality_score = min(1.0, max(0.0, quality_score))

    total_latency_ms = int((time.time() - state["start_time"]) * 1000)
    logger.info(
        "[Total Latency] request_id=%s elapsed_ms=%d",
        req.request_id,
        total_latency_ms,
    )

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    latency_ms = _merge_latency(state, "compute_quality", elapsed_ms)
    logger.info(
        "[Latency Breakdown] request_id=%s total_ms=%d steps=%s",
        req.request_id,
        total_latency_ms,
        latency_ms,
    )

    return {
        "distance_match": distance_match,
        "distance_error_km": distance_error_km,
        "is_fallback_used": is_fallback_used,
        "fallback_reason_str": fallback_reason_str,
        "is_fallback_route": is_fallback_route,
        "quality_score": quality_score,
        "total_latency_ms": total_latency_ms,
        "latency_ms": latency_ms,
    }


async def build_fallback_details(state: AgentState) -> Dict[str, Any]:
    t_start = time.perf_counter()
    fallback_reasons = state["fallback_reasons"]
    fallback_detail_map = {
        "maps_routes_failed": FallbackDetail(
            reason="maps_routes_failed",
            description="ルート生成サービスが利用できませんでした",
            impact="簡易ルートが生成されました。距離は目標に合わせていますが、実際の道順とは異なる場合があります。",
        ),
        "ranker_failed": FallbackDetail(
            reason="ranker_failed",
            description="ルート評価サービスが利用できませんでした",
            impact="ルートの最適化が行われていません。距離や時間は目標に近いですが、最適なルートではない可能性があります。",
        ),
        "vertex_llm_failed": FallbackDetail(
            reason="vertex_llm_failed",
            description="ルート紹介文の生成に失敗しました",
            impact="テンプレートベースの紹介文が使用されています。ルート自体は正常に生成されています。",
        ),
        "invalid_route_detected": FallbackDetail(
            reason="invalid_route_detected",
            description="生成されたルートが無効でした",
            impact="簡易ルートが生成されました。距離は目標に合わせていますが、実際の道順とは異なる場合があります。",
        ),
    }
    fallback_details = [
        fallback_detail_map[reason]
        for reason in fallback_reasons
        if reason in fallback_detail_map
    ]
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "fallback_details": fallback_details,
        "latency_ms": _merge_latency(state, "build_fallback_details", elapsed_ms),
    }


async def store_candidates_bq(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    best_route = state["best_route"]
    candidate_rows: List[Dict[str, Any]] = []
    t_start = time.perf_counter()
    for c in state["candidates"]:
        route_id = c.get("route_id")
        feats = state["candidate_features_map"].get(route_id, {})
        candidate_rows.append({
            "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_id": str(uuid.uuid4()),
            "request_id": req.request_id,
            "route_id": route_id,
            "candidate_index": state["candidate_index_map"].get(route_id),
            "theme": req.theme,
            "round_trip": bool(req.round_trip),
            "fallback": bool(c.get("is_fallback")),
            "chosen_flag": route_id == best_route.get("route_id"),
            "shown_rank": state["shown_rank_map"].get(route_id),
            "features_version": settings.FEATURES_VERSION,
            "ranker_version": settings.RANKER_VERSION,
            "distance_km": feats.get("distance_km"),
            "duration_min": feats.get("duration_min"),
            "loop_closure_m": feats.get("loop_closure_m"),
            "bbox_area": feats.get("bbox_area"),
            "path_length_ratio": feats.get("path_length_ratio"),
            "turn_count": feats.get("turn_count"),
            "turn_density": feats.get("turn_density"),
            "theme_exercise": feats.get("theme_exercise"),
            "theme_think": feats.get("theme_think"),
            "theme_refresh": feats.get("theme_refresh"),
            "theme_nature": feats.get("theme_nature"),
            "round_trip_req": feats.get("round_trip_req"),
            "round_trip_fit": feats.get("round_trip_fit"),
            "distance_error_ratio": feats.get("distance_error_ratio"),
            "relaxation_step": feats.get("relaxation_step"),
            "candidate_rank_in_theme": feats.get("candidate_rank_in_theme"),
            "has_stairs": feats.get("has_stairs"),
            "elevation_gain_m": feats.get("elevation_gain_m"),
            "elevation_density": feats.get("elevation_density"),
            "poi_density": feats.get("poi_density"),
            "park_poi_ratio": feats.get("park_poi_ratio"),
        })
    bq_writer.insert_rows(settings.BQ_TABLE_CANDIDATE, candidate_rows)
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {"latency_ms": _merge_latency(state, "store_candidates_bq", elapsed_ms)}


async def store_proposal_bq(state: AgentState) -> Dict[str, Any]:
    t_start = time.perf_counter()
    req = state["request"]
    best_route = state["best_route"]
    bq_writer.insert_rows(settings.BQ_TABLE_PROPOSAL, [{
        "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": req.request_id,
        "chosen_route_id": best_route["route_id"],
        "fallback_used": state["is_fallback_used"],
        "fallback_reason": state["fallback_reason_str"],
        "tools_used": state["tools_used"],
        "summary_type": state["summary_type"],
        "total_latency_ms": state["total_latency_ms"],
        "features_version": settings.FEATURES_VERSION,
        "ranker_version": settings.RANKER_VERSION,
    }])
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return {"latency_ms": _merge_latency(state, "store_proposal_bq", elapsed_ms)}


async def build_response(state: AgentState) -> Dict[str, Any]:
    req = state["request"]
    best_route = state["best_route"]
    tools_used = state["tools_used"]
    t_start = time.perf_counter()

    with _tracer.start_as_current_span("step.compose_response") as span:
        _set_span_route_attrs(span, req, state)

        route_quality = RouteQuality(
            is_fallback=state["is_fallback_route"],
            distance_match=state["distance_match"],
            distance_error_km=state["distance_error_km"],
            quality_score=state["quality_score"],
        )

        spots = _build_spots_from_places(state["places"])

        meta: Dict[str, Any] = {
            "fallback_used": state["is_fallback_used"],
            "tools_used": tools_used,
            "fallback_reason": state["fallback_reason_str"],
            "fallback_details": state["fallback_details"],
            "route_quality": route_quality,
        }
        if req.debug:
            meta["plan"] = state["plan_steps"]
            meta["debug"] = {
                "routes": {
                    "candidates_count": len(state["candidates"]),
                    "candidates": [
                        {
                            "route_id": c.get("route_id"),
                            "distance_km": c.get("distance_km"),
                            "duration_min": c.get("duration_min"),
                        }
                        for c in state["candidates"][:5]
                    ],
                    "chosen_route_id": best_route.get("route_id"),
                },
                "places": {
                    "spots_count": len(spots),
                    "spots": [{"name": s.name, "type": s.type, "lat": s.lat, "lng": s.lng} for s in spots] if spots else [],
                    "status": state["places_status"],
                },
                "ranker": {
                    "scores_count": len(state["score_map"]),
                    "scores": [
                        {"route_id": route_id, "score": score}
                        for route_id, score in sorted(state["score_map"].items(), key=lambda x: x[1], reverse=True)
                    ],
                    "status": state["ranker_status"],
                },
                "routes_api": {
                    "status": state["routes_api_status"],
                },
            }

        response = GenerateRouteResponse(
            request_id=req.request_id,
            route={
                "route_id": best_route.get("route_id"),
                "polyline": best_route.get("polyline", "xxxx"),
                "distance_km": float(best_route.get("distance_km", req.distance_km)),
                "duration_min": int(best_route.get("duration_min") or 32),
                "title": state["title"],
                "summary": state["description"],
                "nav_waypoints": state["nav_waypoints"],
                "spots": spots,
            },
            meta=meta,
        )
        total_latency_ms = int((time.time() - state["start_time"]) * 1000)
        latency_ms = _merge_latency(state, "build_response", int((time.perf_counter() - t_start) * 1000))
        logger.info(
            "[Latency Summary] request_id=%s total_ms=%d steps=%s",
            req.request_id,
            total_latency_ms,
            latency_ms,
        )
        summary = {
            "message": "route_generate_summary",
            "service": "agent",
            "request_id": req.request_id,
            "path": "/route/generate",
            "fallback": bool(state.get("is_fallback_used")),
            "fallback_reason": state.get("fallback_reason_str"),
            "routes_api_status": state.get("routes_api_status"),
            "places_status": state.get("places_status"),
            "ranker_status": state.get("ranker_status"),
            "candidates_count": len(state.get("candidates") or []),
            "total_latency_ms": total_latency_ms,
            "debug": bool(getattr(req, "debug", False)),
        }
        current_span = trace.get_current_span()
        ctx = current_span.get_span_context()
        trace_id_hex = format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None
        summary["trace_id"] = trace_id_hex
        logger.info(json.dumps(summary, ensure_ascii=False))
        return {"response": response, "latency_ms": latency_ms}


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("validate_request", validate_request)
    graph.add_node("log_request_bq", log_request_bq)
    graph.add_node("generate_candidates_routes", generate_candidates_routes)
    graph.add_node("fallback_candidates", fallback_candidates)
    graph.add_node("compute_features", compute_features)
    graph.add_node("score_by_ranker", score_by_ranker)
    graph.add_node("fallback_ranking", fallback_ranking)
    graph.add_node("select_best_route", select_best_route)
    graph.add_node("sample_points_from_polyline", sample_points_from_polyline)
    graph.add_node("fetch_places", fetch_places)
    graph.add_node("parallel_postprocess", parallel_postprocess)
    graph.add_node("simplify_polyline_to_waypoints", simplify_polyline_to_waypoints)
    graph.add_node("generate_description_vertex", generate_description_vertex)
    graph.add_node("generate_title_vertex", generate_title_vertex)
    graph.add_node("compute_quality", compute_quality)
    graph.add_node("build_fallback_details", build_fallback_details)
    graph.add_node("store_candidates_bq", store_candidates_bq)
    graph.add_node("store_proposal_bq", store_proposal_bq)
    graph.add_node("build_response", build_response)

    graph.set_entry_point("validate_request")
    graph.add_edge("validate_request", "log_request_bq")
    graph.add_edge("log_request_bq", "generate_candidates_routes")
    graph.add_conditional_edges(
        "generate_candidates_routes",
        lambda state: "fallback_candidates"
        if state.get("routes_api_status") != "ok"
        else "compute_features",
    )
    graph.add_edge("fallback_candidates", "compute_features")
    graph.add_edge("compute_features", "score_by_ranker")
    graph.add_conditional_edges(
        "score_by_ranker",
        lambda state: "fallback_ranking"
        if state.get("ranker_status") != "ok"
        else "select_best_route",
    )
    graph.add_edge("fallback_ranking", "select_best_route")
    graph.add_edge("select_best_route", "sample_points_from_polyline")
    graph.add_edge("sample_points_from_polyline", "parallel_postprocess")
    graph.add_edge("parallel_postprocess", "simplify_polyline_to_waypoints")
    graph.add_edge("simplify_polyline_to_waypoints", "compute_quality")
    graph.add_edge("compute_quality", "build_fallback_details")
    graph.add_edge("build_fallback_details", "store_candidates_bq")
    graph.add_edge("store_candidates_bq", "store_proposal_bq")
    graph.add_edge("store_proposal_bq", "build_response")
    graph.add_edge("build_response", END)
    return graph


_route_graph = _build_graph().compile()


async def run_generate_graph(req: GenerateRouteRequest) -> GenerateRouteResponse:
    state = _init_state(req)
    result = await _route_graph.ainvoke(state)
    return result["response"]


def get_route_graph_mermaid() -> str:
    return _route_graph.get_graph().draw_mermaid()
