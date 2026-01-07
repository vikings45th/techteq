from __future__ import annotations
import time
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException
from app.schemas import (
    GenerateRouteRequest,
    GenerateRouteResponse,
    FeedbackRequest,
    FeedbackResponse,
    ToolName,
)
from app.settings import settings
from app.services import ranker_client, bq_writer, fallback, maps_routes_client, places_client, vertex_llm, polyline
from app.services.feature_calc import Candidate, calc_features

app = FastAPI(title="firstdown Agent API", version="1.0.0")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/route/feedback", response_model=FeedbackResponse)
def post_feedback(req: FeedbackRequest) -> FeedbackResponse:
    # Best-effort store
    bq_writer.insert_rows(settings.BQ_TABLE_FEEDBACK, [{
        "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": req.request_id,
        "rating": int(req.rating),
        "note": None,
    }])
    return FeedbackResponse(request_id=req.request_id)


@app.post("/route/generate", response_model=GenerateRouteResponse)
async def generate(req: GenerateRouteRequest) -> GenerateRouteResponse:
    t0 = time.time()
    plan_steps = [
        "generate_candidates",
        "classify_by_theme",
        "select_representatives",
        "featurize",
        "rank_batch",
        "choose_best",
        "summarize",
    ]
    retry_policy = {"distance_relaxation": ["±10%", "±20%", "±30%"]}

    # 1) store request (best-effort)
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

    # 2) Candidate generation via Routes API (fallback to dummy if API disabled)
    tools_used: List[ToolName] = []
    candidates: List[Dict[str, Any]] = []
    relaxation_step = 0
    try:
        candidates = await maps_routes_client.compute_route_candidates(
            request_id=req.request_id,
            start_lat=float(req.start_location.lat),
            start_lng=float(req.start_location.lng),
            distance_km=float(req.distance_km),
            round_trip=bool(req.round_trip),
        )
        if candidates:
            tools_used.append("maps_routes")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"maps_routes failed: {repr(e)}")

    if not candidates:
        # fallback dummy candidates to keep flow alive
        candidates = [
            {"route_id": "r1", "polyline": "xxxx", "distance_km": float(req.distance_km), "duration_min": 32.0},
        ]
        
    # Ensure downstream logic can use theme-based heuristics consistently
    for c in candidates:
        c.setdefault("theme", req.theme)

    # 3) Feature extraction
    rep_routes_payload = []
    for i, c in enumerate(candidates[:5], start=1):
        cand = Candidate(
            route_id=c["route_id"],
            polyline=c.get("polyline", "xxxx"),
            distance_km=float(c.get("distance_km", req.distance_km)),
            duration_min=float(c.get("duration_min") or 30.0 + i),
            loop_closure_m=20.0,
            bbox_area=0.5,
            path_length_ratio=1.3,
            turn_count=10 + i,
        )
        feats = calc_features(
            candidate=cand,
            theme=req.theme,
            round_trip_req=req.round_trip,
            distance_km_target=float(req.distance_km),
            relaxation_step=relaxation_step,
            candidate_rank_in_theme=i,
        )
        rep_routes_payload.append({"route_id": cand.route_id, "features": feats})

    # 4) Call ranker
    tools_used.append("ranker")
    fallback_used = False
    fallback_reason = None

    try:
        scores_list, failed_ids = await ranker_client.rank_routes(req.request_id, rep_routes_payload)
        score_map = {x["route_id"]: float(x["score"]) for x in scores_list if "route_id" in x and "score" in x}
    except Exception:
        score_map = {}
        failed_ids = [x["route_id"] for x in rep_routes_payload]
        fallback_used = True
        fallback_reason = "ranker_timeout"

    # 5) Choose best
    chosen = fallback.choose_best_route(candidates, score_map, req.theme)
    if chosen is None:
        raise HTTPException(status_code=422, detail="No viable route found")

    # 6) Summary and POIs
    spots: List[Dict[str, Any]] = []
    try:
        encoded = (chosen.get("polyline") or "").strip()
        sample_latlngs: List[tuple[float, float]] = []

        if encoded and encoded != "xxxx":
            pts = polyline.decode_polyline(encoded)
            sample_latlngs = polyline.sample_points(pts, [0.25, 0.5, 0.75])

        # Fallback to start point if decode failed or dummy
        encoded = (chosen.get("polyline") or "").strip()
        sample_latlngs: List[tuple[float, float]] = []

        if encoded and encoded != "xxxx":
            pts = polyline.decode_polyline(encoded)
            sample_latlngs = polyline.sample_points(pts, [0.25, 0.5, 0.75])

        # Fallback to start point if decode failed or dummy
        if not sample_latlngs:
            sample_latlngs = [(float(req.start_location.lat), float(req.start_location.lng))]

        merged: List[Dict[str, Any]] = []
        seen_names = set()
        for (lat, lng) in sample_latlngs:
            found = await places_client.search_spots(lat=float(lat), lng=float(lng), radius_m=800, max_results=3)
            for p in found:
                name = p.get("name")
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                merged.append(p)
            if len(merged) >= 5:
                break

        spots = merged[:5]
        if spots:
            tools_used.append("places")
    except Exception:
        spots = []

    summary = "【簡易提案】条件に合わせた散歩ルートです"
    summary_type = "template"
    try:
        vertex_summary = await vertex_llm.generate_summary(
            theme=req.theme,
            distance_km=float(chosen.get("distance_km", req.distance_km)),
            duration_min=float(chosen.get("duration_min") or 30.0),
            spots=spots,
        )
        if vertex_summary:
            summary = vertex_summary
            summary_type = "vertex_llm"
            tools_used.append("vertex_llm")
    except Exception:
        pass

    total_latency_ms = int((time.time() - t0) * 1000)

    # 7) store proposal (best-effort)
    bq_writer.insert_rows(settings.BQ_TABLE_PROPOSAL, [{
        "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": req.request_id,
        "chosen_route_id": chosen["route_id"],
        "fallback_used": bool(fallback_used),
        "fallback_reason": fallback_reason,
        "tools_used": tools_used,
        "summary_type": summary_type,
        "total_latency_ms": total_latency_ms,
    }])

    meta = {
        "fallback_used": fallback_used,
        "tools_used": tools_used,
    }
    if fallback_reason:
        meta["fallback_reason"] = fallback_reason
    if req.debug:
        meta["plan"] = plan_steps
        meta["retry_policy"] = retry_policy

    return GenerateRouteResponse(
        request_id=req.request_id,
        route={
            "polyline": chosen.get("polyline", "xxxx"),
            "distance_km": float(chosen.get("distance_km", req.distance_km)),
            "duration_min": int(chosen.get("duration_min") or 32),
            "summary": summary,
            "spots": spots,
        },
        meta=meta,
    )
