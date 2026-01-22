from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RankRoute(BaseModel):
    """スコアリング対象のルート情報"""
    route_id: str  # ルートID
    features: Dict[str, Any] = Field(default_factory=dict)  # 機械学習用の特徴量辞書


class RankRequest(BaseModel):
    """ランキングリクエストのスキーマ"""
    request_id: Optional[str] = None  # リクエストID（ログ用）
    routes: List[RankRoute] = Field(min_length=1, max_length=5)  # スコアリング対象のルートリスト（1〜5件）


class ScoreItem(BaseModel):
    """スコアリング結果の1件"""
    route_id: str  # ルートID
    score: float  # スコア（0.0-1.0、高いほど良い）
    breakdown: Optional[Dict[str, Any]] = None  # スコア内訳（デバッグ用、各要素の寄与度）


class RankResponse(BaseModel):
    """ランキングレスポンスのスキーマ"""
    scores: List[ScoreItem] = Field(default_factory=list)  # スコアリング成功したルートのリスト
    failed_route_ids: List[str] = Field(default_factory=list)  # スコアリングに失敗したルートIDのリスト
