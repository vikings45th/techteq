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
    polyline: str
    distance_km: float
    duration_min: int
    summary: str
    spots: List[Spot] = []


class RouteQuality(BaseModel):
    """ルート品質情報（UI表示用）"""
    is_fallback: bool = Field(..., description="フォールバックルートかどうか")
    distance_match: float = Field(..., description="距離整合性（0.0-1.0、1.0が完全一致）")
    distance_error_km: float = Field(..., description="距離誤差（km、絶対値）")
    quality_score: Optional[float] = Field(None, description="品質スコア（0.0-1.0、高いほど良い）")


class FallbackDetail(BaseModel):
    """フォールバック理由の詳細（UI表示用）"""
    reason: str = Field(..., description="フォールバック理由コード")
    description: str = Field(..., description="ユーザー向け説明文")
    impact: str = Field(..., description="影響の説明（例: 'ルート品質が低下'）")


class MetaOut(BaseModel):
    fallback_used: bool
    tools_used: List[ToolName]
    fallback_reason: Optional[str] = None
    fallback_details: List[FallbackDetail] = Field(default_factory=list, description="フォールバック理由の詳細リスト")
    route_quality: RouteQuality = Field(..., description="ルート品質情報")
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
