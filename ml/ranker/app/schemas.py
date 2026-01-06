from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RankRoute(BaseModel):
    route_id: str
    features: Dict[str, Any] = Field(default_factory=dict)


class RankRequest(BaseModel):
    request_id: str
    routes: List[RankRoute] = Field(min_length=1, max_length=5)


class ScoreItem(BaseModel):
    route_id: str
    score: float


class RankResponse(BaseModel):
    scores: List[ScoreItem] = Field(default_factory=list)
    failed_route_ids: List[str] = Field(default_factory=list)
