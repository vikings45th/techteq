from typing import List, Literal, Optional
from pydantic import BaseModel, Field, conint, confloat


# テーマの型定義（散歩の目的・雰囲気）
Theme = Literal["exercise", "think", "refresh", "nature"]
# 使用したツール名の型定義
ToolName = Literal["maps_routes", "places", "ranker", "vertex_llm"]


class LatLng(BaseModel):
    """緯度経度を表すデータクラス"""
    lat: confloat(ge=-90, le=90)  # 緯度（-90〜90度）
    lng: confloat(ge=-180, le=180)  # 経度（-180〜180度）


class GenerateRouteRequest(BaseModel):
    """ルート生成リクエストのスキーマ"""
    request_id: str = Field(..., description="UUID")  # リクエストID（UUID形式）
    theme: Theme  # テーマ（"exercise", "think", "refresh", "nature"）
    distance_km: confloat(gt=0)  # 目標距離（km、0より大きい値）
    start_location: LatLng  # 開始地点の緯度経度
    round_trip: bool  # 往復ルートかどうか
    debug: bool = False  # デバッグモード（追加情報を返すかどうか）


class Spot(BaseModel):
    """見どころスポットの情報"""
    name: str  # スポット名
    type: str  # スポットタイプ（例: "park", "cafe"）


class RouteOut(BaseModel):
    """生成されたルート情報"""
    route_id: str  # ルートID（UUID）
    polyline: str  # エンコードされたpolyline文字列（地図表示用）
    distance_km: float  # 距離（km）
    duration_min: int  # 所要時間（分）
    summary: str  # ルートの紹介文
    spots: List[Spot] = []  # ルート上の見どころスポットのリスト


class RouteQuality(BaseModel):
    """
    ルート品質情報（UI表示用）
    
    ルートの品質を評価するための情報を格納する。
    """
    is_fallback: bool = Field(..., description="フォールバックルートかどうか")  # フォールバック使用フラグ
    distance_match: float = Field(..., description="距離整合性（0.0-1.0、1.0が完全一致）")  # 距離整合性スコア
    distance_error_km: float = Field(..., description="距離誤差（km、絶対値）")  # 目標距離との誤差
    quality_score: Optional[float] = Field(None, description="品質スコア（0.0-1.0、高いほど良い）")  # 総合品質スコア


class FallbackDetail(BaseModel):
    """
    フォールバック理由の詳細（UI表示用）
    
    フォールバックが使用された理由とその影響を説明する情報。
    """
    reason: str = Field(..., description="フォールバック理由コード")  # 理由コード（例: "maps_routes_failed"）
    description: str = Field(..., description="ユーザー向け説明文")  # ユーザー向けの説明文
    impact: str = Field(..., description="影響の説明（例: 'ルート品質が低下'）")  # フォールバックによる影響の説明


class MetaOut(BaseModel):
    """レスポンスのメタ情報"""
    fallback_used: bool  # フォールバックが使用されたかどうか
    tools_used: List[ToolName]  # 使用したツールのリスト
    fallback_reason: Optional[str] = None  # フォールバック理由（カンマ区切り文字列）
    fallback_details: List[FallbackDetail] = Field(default_factory=list, description="フォールバック理由の詳細リスト")  # フォールバック詳細のリスト
    route_quality: RouteQuality = Field(..., description="ルート品質情報")  # ルート品質情報
    plan: Optional[List[str]] = None  # 処理ステップのリスト（デバッグ用）
    retry_policy: Optional[dict] = None  # リトライポリシー（デバッグ用）


class GenerateRouteResponse(BaseModel):
    """ルート生成レスポンスのスキーマ"""
    request_id: str  # リクエストID
    route: RouteOut  # 生成されたルート情報
    meta: MetaOut  # メタ情報（フォールバック情報、品質情報など）


class FeedbackRequest(BaseModel):
    """フィードバックリクエストのスキーマ"""
    request_id: str  # リクエストID（フィードバック対象のルート生成リクエストID）
    route_id: str  # ルートID（UUID）
    rating: conint(ge=1, le=5)  # 評価（1〜5の整数）


class FeedbackResponse(BaseModel):
    """フィードバックレスポンスのスキーマ"""
    request_id: str  # リクエストID
    status: Literal["accepted"] = "accepted"  # ステータス（常に"accepted"）
