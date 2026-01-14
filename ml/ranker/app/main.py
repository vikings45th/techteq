from __future__ import annotations
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from app.schemas import RankRequest, RankResponse, ScoreItem
from app.settings import settings

app = FastAPI(title="firstdown Ranker API", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


def _calculate_score(features: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    """
    ルールベーススコアリング: 距離乖離 / loop closure / POI数を考慮
    
    Args:
        features: ルートの特徴量辞書
    
    Returns:
        (score, breakdown): スコア（0.0-1.0）と内訳のタプル
    """
    # 1. 距離乖離ペナルティ（距離誤差が小さいほど良い）
    distance_error_ratio = float(features.get("distance_error_ratio", 0.0))  # 距離誤差比率
    distance_penalty = -distance_error_ratio * 0.5  # 誤差が大きいほど減点
    
    # 2. Loop closure ボーナス（往復ルート適合度）
    round_trip_req = features.get("round_trip_req", 0)  # 往復ルート要求フラグ
    round_trip_fit = features.get("round_trip_fit", 0)  # 往復ルート適合フラグ
    loop_closure_bonus = 0.0
    if round_trip_req:
        # 往復ルートが要求されている場合、loop_closure_mが小さいほど良い
        loop_closure_m = float(features.get("loop_closure_m", 1000.0))  # ループ閉鎖距離（m）
        if loop_closure_m <= 100.0:
            loop_closure_bonus = 0.2  # 100m以内ならボーナス
        elif loop_closure_m <= 500.0:
            loop_closure_bonus = 0.1  # 500m以内なら小さいボーナス
        # round_trip_fitも考慮（後方互換性）
        if round_trip_fit:
            loop_closure_bonus = max(loop_closure_bonus, 0.2)
    
    # 3. POI 数ボーナス（park_poi_ratioとpoi_densityを考慮）
    park_poi_ratio = float(features.get("park_poi_ratio", 0.0))  # 公園POI比率
    poi_density = float(features.get("poi_density", 0.0))  # POI密度
    poi_bonus = park_poi_ratio * 0.15 + min(poi_density, 1.0) * 0.1  # 上限あり（poi_densityは1.0でクランプ）
    
    # 4. Exerciseテーマの場合: 坂道と階段のボーナス
    exercise_bonus = 0.0
    theme_exercise = features.get("theme_exercise", 0)  # 運動テーマフラグ
    if theme_exercise:
        # 階段がある場合のボーナス（運動強度が高い）
        has_stairs = features.get("has_stairs", 0)  # 階段の有無
        if has_stairs:
            exercise_bonus += 0.15  # 階段があると運動強度が高い
        
        # 標高差密度（m/km）に基づくボーナス
        elevation_density = float(features.get("elevation_density", 0.0))  # 標高差密度（m/km）
        # 適度な坂道（10-50m/km）が理想的
        if 10.0 <= elevation_density <= 50.0:
            exercise_bonus += 0.2  # 適度な坂道は良い
        elif 5.0 <= elevation_density < 10.0:
            exercise_bonus += 0.1  # 軽い坂道も良い
        elif elevation_density > 50.0:
            exercise_bonus += 0.1  # 急な坂道も運動強度は高いが、やや減点
        # 0-5m/kmは平地でボーナスなし
    
    # ベーススコア
    base = 0.5
    
    # 合計スコアを計算
    score = base + distance_penalty + loop_closure_bonus + poi_bonus + exercise_bonus
    score = max(0.0, min(1.0, score))  # 0.0-1.0の範囲にクリップ
    
    # 内訳（デバッグ用）
    breakdown = {
        "base": base,  # ベーススコア
        "distance_penalty": distance_penalty,  # 距離乖離ペナルティ
        "loop_closure_bonus": loop_closure_bonus,  # ループ閉鎖ボーナス
        "poi_bonus": poi_bonus,  # POIボーナス
        "exercise_bonus": exercise_bonus,  # 運動ボーナス
        "final_score": score,  # 最終スコア
    }
    
    return score, breakdown


@app.post("/rank", response_model=RankResponse)
def rank(req: RankRequest) -> RankResponse:
    """
    ルート候補をスコアリングしてランキングする
    
    MVP: ルールベースのスタブ実装。後でVertex AIに置き換え予定。
    
    スコアリングロジック:
    - 距離乖離: 目標距離との誤差が小さいほど良い（ペナルティ方式）
    - Loop closure: 往復ルート要求時、loop_closure_mが小さいほど良い
    - POI数: park_poi_ratioとpoi_densityが高いほど良い
    - Exerciseテーマ: 階段の有無と標高差密度（坂道の程度）を考慮
      - 階段がある: +0.15
      - 標高差密度10-50m/km（適度な坂道）: +0.2
      - 標高差密度5-10m/km（軽い坂道）: +0.1
      - 標高差密度50m/km以上（急な坂道）: +0.1
    
    Args:
        req: ランキングリクエスト（ルート候補のリスト）
    
    Returns:
        スコアリング結果（スコア順にソート済み）
    
    Raises:
        HTTPException: すべてのルートのスコアリングに失敗した場合（422）
    """
    scores = []  # 成功したスコアのリスト
    failed = []  # 失敗したルートIDのリスト

    # 各ルートをスコアリング
    for r in req.routes:
        try:
            score, breakdown = _calculate_score(r.features)
            scores.append(ScoreItem(route_id=r.route_id, score=score, breakdown=breakdown))
        except Exception as e:
            # スコアリングに失敗したルートIDを記録
            failed.append(r.route_id)

    # すべて失敗した場合はエラー
    if len(scores) == 0:
        raise HTTPException(status_code=422, detail="No successful inference")

    # スコア順にソート（高い順）
    scores.sort(key=lambda x: x.score, reverse=True)

    return RankResponse(scores=scores, failed_route_ids=failed)
