from typing import List, Literal, Optional
from pydantic import BaseModel, Field, conint, confloat


Theme = Literal["exercise", "think", "refresh", "nature"]
ToolName = Literal["maps_routes", "places", "ranker", "vertex_llm"]


class LatLng(BaseModel):
    lat: confloat(ge=-90, le=90)
    lng: confloat(ge=-180, le=180)


class GenerateRouteRequest(BaseModel):
    request_id: str = Field(..., description="UUID")
    theme: Theme
    distance_km: confloat(gt=0)
    start_location: LatLng
    round_trip: bool
    debug: bool = False


class Spot(BaseModel):
    name: str
    type: str


class RouteOut(BaseModel):
    polyline: List[LatLng]
    distance_km: float
    duration_min: int
    summary: str
    spots: List[Spot] = []


class MetaOut(BaseModel):
    fallback_used: bool
    tools_used: List[ToolName]
    fallback_reason: Optional[str] = None
    plan: Optional[List[str]] = None
    retry_policy: Optional[dict] = None


class GenerateRouteResponse(BaseModel):
    request_id: str
    route: RouteOut
    meta: MetaOut


class FeedbackRequest(BaseModel):
    request_id: str
    rating: conint(ge=1, le=5)


class FeedbackResponse(BaseModel):
    request_id: str
    status: Literal["accepted"] = "accepted"
