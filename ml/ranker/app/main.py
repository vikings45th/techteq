from __future__ import annotations
from fastapi import FastAPI, HTTPException
from app.schemas import RankRequest, RankResponse, ScoreItem
from app.settings import settings

app = FastAPI(title="firstdown Ranker API", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/rank", response_model=RankResponse)
def rank(req: RankRequest) -> RankResponse:
    # MVP: rule-based stub scoring. Replace with Vertex AI later.
    scores = []
    failed = []

    for r in req.routes:
        try:
            f = r.features
            # Simple deterministic score (example):
            # prefer smaller distance_error_ratio and round_trip_fit when requested
            base = 0.5
            base -= float(f.get("distance_error_ratio", 0.0)) * 0.5
            base += float(f.get("round_trip_fit", 0.0)) * 0.2
            base += float(f.get("park_poi_ratio", 0.0)) * 0.2
            score = max(0.0, min(1.0, base))
            scores.append(ScoreItem(route_id=r.route_id, score=score))
        except Exception:
            failed.append(r.route_id)

    if len(scores) == 0:
        raise HTTPException(status_code=422, detail="No successful inference")

    return RankResponse(scores=scores, failed_route_ids=failed)
