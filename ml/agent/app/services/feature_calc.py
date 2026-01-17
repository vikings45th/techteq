from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class Candidate:
    """ルート候補のデータクラス"""
    route_id: str  # ルートID
    polyline: str  # エンコードされたpolyline文字列
    distance_km: float  # 距離（km）
    duration_min: float  # 所要時間（分）
    # MVP: 最小限の特徴量を保持（後で拡張可能）
    loop_closure_m: float  # ループ閉鎖距離（m）- 往復ルートの場合の開始地点との距離
    bbox_area: float  # バウンディングボックスの面積
    path_length_ratio: float  # パス長比率（実際の距離/直線距離）
    turn_count: int  # 曲がり角の数
    # 運動関連の特徴量
    has_stairs: bool = False  # 階段を含むかどうか
    elevation_gain_m: float = 0.0  # 累積標高差（m、上り方向のみ）


def calc_features(
    *,
    candidate: Candidate,
    theme: str,
    round_trip_req: bool,
    distance_km_target: float,
    relaxation_step: int,
    candidate_rank_in_theme: int,
    poi_density: float = 0.0,
    park_poi_ratio: float = 0.0,
    spot_type_diversity: float = 0.0,
    detour_over_ratio: float = 0.0,
    detour_allowance_m: float = 0.0,
) -> Dict[str, Any]:
    """
    ルート候補から機械学習用の特徴量を計算する
    
    Args:
        candidate: ルート候補データ
        theme: テーマ（"exercise", "think", "refresh", "nature"）
        round_trip_req: 往復ルートが要求されているか
        distance_km_target: 目標距離（km）
        relaxation_step: 距離緩和ステップ（リトライ回数）
        candidate_rank_in_theme: テーマ内での候補の順位
        poi_density: POI密度（オプション、MVPでは0.0）
        park_poi_ratio: 公園POI比率（オプション、MVPでは0.0）
    
    Returns:
        特徴量の辞書
    """
    # 派生特徴量の計算
    turn_density = candidate.turn_count / max(candidate.distance_km, 1e-6)  # 曲がり角密度（回/km）
    distance_error_ratio = abs(candidate.distance_km - distance_km_target) / max(distance_km_target, 1e-6)  # 距離誤差比率
    round_trip_fit = 1 if candidate.loop_closure_m <= 100.0 else 0  # 往復ルート適合度（100m以内なら1）
    
    # 運動関連の特徴量
    has_stairs = 1 if candidate.has_stairs else 0  # 階段の有無（0/1）
    elevation_gain_m = float(candidate.elevation_gain_m)  # 累積標高差（m）
    # 標高差密度（標高差/距離）: 運動強度の指標（m/km）
    elevation_density = elevation_gain_m / max(candidate.distance_km * 1000.0, 1.0)  # m/km

    # テーマのワンホットエンコーディング
    theme_exercise = 1 if theme == "exercise" else 0
    theme_think = 1 if theme == "think" else 0
    theme_refresh = 1 if theme == "refresh" else 0
    theme_nature = 1 if theme == "nature" else 0

    return {
        # 基本特徴量
        "distance_km": float(candidate.distance_km),  # 距離（km）
        "duration_min": float(candidate.duration_min),  # 所要時間（分）
        "loop_closure_m": float(candidate.loop_closure_m),  # ループ閉鎖距離（m）
        "bbox_area": float(candidate.bbox_area),  # バウンディングボックス面積
        "path_length_ratio": float(candidate.path_length_ratio),  # パス長比率
        "turn_count": int(candidate.turn_count),  # 曲がり角の数
        "turn_density": float(turn_density),  # 曲がり角密度（回/km）

        # テーマ特徴量（ワンホットエンコーディング）
        "theme_exercise": theme_exercise,  # 運動テーマ
        "theme_think": theme_think,  # 思考テーマ
        "theme_refresh": theme_refresh,  # リフレッシュテーマ
        "theme_nature": theme_nature,  # 自然テーマ

        # リクエスト関連特徴量
        "round_trip_req": 1 if round_trip_req else 0,  # 往復ルート要求（0/1）
        "round_trip_fit": int(round_trip_fit),  # 往復ルート適合度（0/1）
        "distance_error_ratio": float(distance_error_ratio),  # 距離誤差比率

        # メタ特徴量
        "relaxation_step": int(relaxation_step),  # 距離緩和ステップ
        "candidate_rank_in_theme": int(candidate_rank_in_theme),  # テーマ内での順位

        # 運動関連特徴量
        "has_stairs": int(has_stairs),  # 階段の有無（0/1）
        "elevation_gain_m": float(elevation_gain_m),  # 累積標高差（m）
        "elevation_density": float(elevation_density),  # 標高差密度（m/km）

        # オプション特徴量（MVP: 利用不可の場合は0.0）
        "poi_density": float(poi_density),  # POI密度
        "park_poi_ratio": float(park_poi_ratio),  # 公園POI比率
        "spot_type_diversity": float(spot_type_diversity),  # スポットタイプ多様性
        "detour_over_ratio": float(detour_over_ratio),  # 寄り道超過比率
        "detour_allowance_m": float(detour_allowance_m),  # 許容寄り道距離（m）
    }
