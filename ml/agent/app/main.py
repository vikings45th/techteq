from __future__ import annotations
import time
import logging
import uuid
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException
from app.schemas import (
    GenerateRouteRequest,
    GenerateRouteResponse,
    FeedbackRequest,
    FeedbackResponse,
    ToolName,
    Spot,
    LatLng,
    RouteQuality,
    FallbackDetail,
)
from app.settings import settings
from app.services import ranker_client, bq_writer, fallback, maps_routes_client, places_client, vertex_llm, polyline
from app.services.feature_calc import Candidate, calc_features
import polyline as polyline_lib

app = FastAPI(title="firstdown Agent API", version="1.0.0")

logger = logging.getLogger(__name__)


def translate_place_type_to_japanese(place_type: str) -> str:
    """
    Places APIの場所タイプを日本語に変換する
    
    Args:
        place_type: Places APIの場所タイプ（例: "park", "cafe"）
    
    Returns:
        日本語の場所タイプ名
    """
    type_mapping: Dict[str, str] = {
        "park": "公園",
        "gym": "ジム",
        "sports_complex": "スポーツ施設",
        "fitness_center": "フィットネスセンター",
        "hiking_area": "ハイキングエリア",
        "cycling_park": "サイクリングパーク",
        "stadium": "スタジアム",
        "sports_club": "スポーツクラブ",
        "sports_activity_location": "スポーツ活動場所",
        "swimming_pool": "プール",
        "athletic_field": "運動場",
        "playground": "遊び場",
        "arena": "アリーナ",
        "library": "図書館",
        "museum": "博物館",
        "cafe": "カフェ",
        "art_gallery": "美術館",
        "book_store": "書店",
        "university": "大学",
        "school": "学校",
        "auditorium": "講堂",
        "cultural_center": "文化センター",
        "performing_arts_theater": "劇場",
        "restaurant": "レストラン",
        "tourist_attraction": "観光スポット",
        "beach": "ビーチ",
        "botanical_garden": "植物園",
        "garden": "庭園",
        "plaza": "広場",
        "observation_deck": "展望台",
        "amusement_park": "遊園地",
        "water_park": "ウォーターパーク",
        "national_park": "国立公園",
        "state_park": "州立公園",
        "wildlife_park": "野生動物公園",
        "wildlife_refuge": "野生動物保護区",
        "zoo": "動物園",
        "unknown": "その他",
    }
    return type_mapping.get(place_type, place_type)  # マッピングがない場合は元の値を返す


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/route/feedback", response_model=FeedbackResponse)
def post_feedback(req: FeedbackRequest) -> FeedbackResponse:
    # Best-effort store
    bq_writer.insert_rows(settings.BQ_TABLE_FEEDBACK, [{
        "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": req.request_id,
        "route_id": req.route_id,
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

    # 1) store request
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

    # 【修正】エラー理由を蓄積するリストを定義
    fallback_reasons: List[str] = []

    # 2) Candidate generation
    tools_used: List[ToolName] = []
    candidates: List[Dict[str, Any]] = []
    relaxation_step = 0
    
    # --- API呼び出し ---
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
        logger.warning("[Maps Routes Failed] request_id=%s err=%r", req.request_id, e)

    # --- Fallback処理 ---
    if not candidates:
        # 【修正】Maps失敗として記録
        fallback_reasons.append("maps_routes_failed")

        start_lat = float(req.start_location.lat)
        start_lng = float(req.start_location.lng)
        
        # 必ずダミーpolylineを生成（空対策の保証）
        fallback_points = [
            (start_lat, start_lng),
            (start_lat + 0.0001, start_lng + 0.0001)
        ]
        safe_polyline = ""
        try:
            safe_polyline = polyline_lib.encode(fallback_points)
        except Exception as e:
            logger.warning("[Fallback Polyline Error] request_id=%s err=%r", req.request_id, e)
            # エラー時も最小限のpolylineを生成（2点間の短い距離）
            try:
                # より単純なフォールバック: 開始地点と少し離れた地点
                safe_polyline = polyline_lib.encode([(start_lat, start_lng), (start_lat + 0.001, start_lng + 0.001)])
            except Exception:
                # それでも失敗した場合は最小限のエンコード済みpolylineを使用
                safe_polyline = "~oia@"  # 最小限の有効なpolyline（東京駅付近の短い線）
        
        # polylineが空の場合は必ずデフォルト値を設定
        if not safe_polyline or safe_polyline.strip() == "":
            safe_polyline = "~oia@"  # 最小限の有効なpolyline

        candidates = [
            {
                "route_id": "fallback_dummy",
                "polyline": safe_polyline,
                "distance_km": float(req.distance_km),
                "duration_min": 32.0,
                "theme": req.theme,
                "is_fallback": True,
            },
        ]
        
    # 候補ごとにUUIDを付与（リクエスト間で衝突しないように統一）
    for c in candidates:
        c["route_id"] = str(uuid.uuid4())
        c.setdefault("is_fallback", False)
        c.setdefault("theme", req.theme)

    # 3) Feature extraction
    # 候補全件の特徴量を算出し、上位5件のみrankerに送信
    rep_routes_payload = []
    candidate_features: Dict[str, Dict[str, Any]] = {}
    candidate_index_map: Dict[str, int] = {}
    for i, c in enumerate(candidates, start=1):
        cand = Candidate(
            route_id=c["route_id"],
            polyline=c.get("polyline", "xxxx"),
            distance_km=float(c.get("distance_km", req.distance_km)),
            duration_min=float(c.get("duration_min") or 30.0 + i),
            loop_closure_m=20.0,
            bbox_area=0.5,
            path_length_ratio=1.3,
            turn_count=10 + i,
            has_stairs=c.get("has_stairs", False),
            elevation_gain_m=float(c.get("elevation_gain_m", 0.0)),
        )
        feats = calc_features(
            candidate=cand,
            theme=req.theme,
            round_trip_req=req.round_trip,
            distance_km_target=float(req.distance_km),
            relaxation_step=relaxation_step,
            candidate_rank_in_theme=i,
        )
        candidate_features[cand.route_id] = feats
        candidate_index_map[cand.route_id] = i
        if i <= 5:
            rep_routes_payload.append({"route_id": cand.route_id, "features": feats})

    # 4) Call ranker
    try:
        scores_list, failed_ids = await ranker_client.rank_routes(req.request_id, rep_routes_payload)
        score_map = {x["route_id"]: float(x["score"]) for x in scores_list if "route_id" in x and "score" in x}
        
        if score_map:
            tools_used.append("ranker")
        else:
            # スコアが空だった場合も失敗とみなす（422エラーや全ルート失敗時）
            score_map = {}
            fallback_reasons.append("ranker_failed")
            logger.warning("[Ranker Empty] request_id=%s no scores returned", req.request_id)
            
    except Exception as e:
        score_map = {}
        # 【修正】Ranker失敗として記録（タイムアウト、ネットワークエラー等）
        fallback_reasons.append("ranker_failed")
        logger.error("[Ranker Error] request_id=%s err=%r", req.request_id, e)

    # 5) Choose best
    chosen = fallback.choose_best_route(candidates, score_map, req.theme)
    if chosen is None:
        raise HTTPException(status_code=422, detail="No viable route found")

    # UI提示順（score順）を算出
    shown_rank_map: Dict[str, int] = {}
    if score_map:
        for rank, (route_id, _score) in enumerate(
            sorted(score_map.items(), key=lambda x: x[1], reverse=True), start=1
        ):
            shown_rank_map[route_id] = rank

    # 6) Summary and POIs
    # polyline 25/50/75% 点から nearby 検索（decode + サンプル点抽出前提）
    spots: List[Spot] = []
    try:
        encoded = (chosen.get("polyline") or "").strip()
        sample_latlngs: List[tuple[float, float]] = []

        # polylineをデコードしてサンプル点（25/50/75%）を抽出
        if encoded and encoded != "xxxx":
            pts = polyline.decode_polyline(encoded)
            sample_latlngs = polyline.sample_points(pts, [0.25, 0.5, 0.75])

        if not sample_latlngs:
            sample_latlngs = [(float(req.start_location.lat), float(req.start_location.lng))]

        logger.info(
            "[Places] request_id=%s sample_latlngs=%d points: %s",
            req.request_id,
            len(sample_latlngs),
            sample_latlngs,
        )

        # Places 重複排除: name（または place_id）基準
        # Places 上限件数制御: 全体 max 件数（5件）が保証される
        merged: List[Dict[str, Any]] = []
        seen_names = set()
        seen_place_ids = set()
        max_spots = 5  # 全体の上限件数

        for (lat, lng) in sample_latlngs:
            # 既に上限に達している場合は検索をスキップ
            if len(merged) >= max_spots:
                break
            
            # themeに応じた場所タイプで検索（「それっぽい」体験に寄せる）
            logger.debug(
                "[Places] request_id=%s searching at (%.6f, %.6f) theme=%s",
                req.request_id,
                lat,
                lng,
                req.theme,
            )
            found = await places_client.search_spots(
                lat=float(lat),
                lng=float(lng),
                theme=req.theme,
                radius_m=800,
                max_results=3,
            )
            logger.info(
                "[Places] request_id=%s found %d places at (%.6f, %.6f): %s",
                req.request_id,
                len(found),
                lat,
                lng,
                [p.get("name") for p in found],
            )
            for p in found:
                # 上限に達したら終了
                if len(merged) >= max_spots:
                    break
                
                name = p.get("name")
                place_id = p.get("place_id")
                
                # nameまたはplace_idが空の場合はスキップ
                if not name:
                    continue
                
                # 重複チェック: place_id優先、なければnameで判定
                is_duplicate = False
                if place_id:
                    if place_id in seen_place_ids:
                        is_duplicate = True
                    else:
                        seen_place_ids.add(place_id)
                else:
                    # place_idがない場合はnameで判定
                    if name in seen_names:
                        is_duplicate = True
                    else:
                        seen_names.add(name)
                
                if not is_duplicate:
                    merged.append(p)
        # 上限件数まで取得（既にmax_spots以下になっているはずだが、念のため）
        spots_raw = merged[:max_spots]
        # DictをSpotオブジェクトに変換（typeを日本語化）
        spots = [
            Spot(
                name=p.get("name", ""),
                type=translate_place_type_to_japanese(p.get("type", "unknown"))
            )
            for p in spots_raw
            if p.get("name")
        ]
        if spots:
            tools_used.append("places")
            logger.info("[Places] request_id=%s found %d spots: %s", req.request_id, len(spots), [s.name for s in spots])
        else:
            logger.info("[Places] request_id=%s no spots found", req.request_id)
    except Exception as e:
        logger.error("[Places Error] request_id=%s err=%r", req.request_id, e)
        spots = []

    # フォールバック用のテンプレートsummary（spots情報を含む）
    spots_names = [s.name for s in spots] if spots else []
    spots_text = f"（見どころ: {', '.join(spots_names)}）" if spots_names else ""
    summary = f"【簡易提案!】条件に合わせた散歩ルートです{spots_text}"
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
        else:
            # Vertexからの応答が空だった場合
            fallback_reasons.append("vertex_llm_failed")
            logger.warning("[Vertex LLM Empty] request_id=%s (returned empty)", req.request_id)

    except Exception as e:
        # 【修正】LLM呼び出し例外発生時
        fallback_reasons.append("vertex_llm_failed")
        logger.error("[Vertex LLM Error] request_id=%s err=%r", req.request_id, e)

    total_latency_ms = int((time.time() - t0) * 1000)

    # 【修正】最終的なFallback状態の集計
    is_fallback_used = len(fallback_reasons) > 0
    # リストをカンマ区切り文字列に変換（例: "maps_routes_failed,vertex_llm_failed"）
    fallback_reason_str = ",".join(fallback_reasons) if fallback_reasons else None

    # フォールバック理由の詳細説明（UI表示用）
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
    }
    fallback_details = [
        fallback_detail_map[reason]
        for reason in fallback_reasons
        if reason in fallback_detail_map
    ]

    # 距離整合性の計算（簡易版）
    target_distance_km = float(req.distance_km)
    actual_distance_km = float(chosen.get("distance_km", target_distance_km))
    distance_error_km = abs(actual_distance_km - target_distance_km)
    
    # 距離整合性スコア（0.0-1.0、誤差が小さいほど高い）
    # 誤差が10%以内なら1.0、50%以上なら0.0、その間は線形補間
    distance_error_ratio = distance_error_km / target_distance_km if target_distance_km > 0 else 1.0
    if distance_error_ratio <= 0.1:
        distance_match = 1.0
    elif distance_error_ratio >= 0.5:
        distance_match = 0.0
    else:
        # 0.1-0.5の間を線形補間: 0.1→1.0, 0.5→0.0
        distance_match = 1.0 - ((distance_error_ratio - 0.1) / 0.4)
    
    # フォールバックルートかどうかの判定
    is_fallback_route = bool(chosen.get("is_fallback")) or is_fallback_used
    
    # 品質スコアの計算（簡易版）
    # フォールバック: 0.3、距離整合性が良い: +0.4、ツールが使われている: +0.3
    quality_score = 0.0
    if not is_fallback_route:
        quality_score += 0.3  # 通常ルートのベーススコア
    quality_score += distance_match * 0.4  # 距離整合性
    if len(tools_used) >= 3:  # 主要ツール（maps_routes, ranker, places）が使われている
        quality_score += 0.3
    quality_score = min(1.0, max(0.0, quality_score))  # 0.0-1.0にクリップ

    # 7) store candidates (training data)
    candidate_rows: List[Dict[str, Any]] = []
    for c in candidates:
        route_id = c.get("route_id")
        feats = candidate_features.get(route_id, {})
        candidate_rows.append({
            "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_id": str(uuid.uuid4()),
            "request_id": req.request_id,
            "route_id": route_id,
            "candidate_index": candidate_index_map.get(route_id),
            "theme": req.theme,
            "round_trip": bool(req.round_trip),
            "fallback": bool(c.get("is_fallback")),
            "chosen_flag": route_id == chosen.get("route_id"),
            "shown_rank": shown_rank_map.get(route_id),
            "features_version": settings.FEATURES_VERSION,
            "ranker_version": settings.RANKER_VERSION,
            # フラット化した特徴量
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

    # 8) store proposal
    bq_writer.insert_rows(settings.BQ_TABLE_PROPOSAL, [{
        "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": req.request_id,
        "chosen_route_id": chosen["route_id"],
        "fallback_used": is_fallback_used,       # 【修正】
        "fallback_reason": fallback_reason_str,  # 【修正】
        "tools_used": tools_used,
        "summary_type": summary_type,
        "total_latency_ms": total_latency_ms,
        "features_version": settings.FEATURES_VERSION,
        "ranker_version": settings.RANKER_VERSION,
    }])

    # ルート品質情報の構築
    route_quality = RouteQuality(
        is_fallback=is_fallback_route,
        distance_match=distance_match,
        distance_error_km=distance_error_km,
        quality_score=quality_score,
    )

    meta = {
        "fallback_used": is_fallback_used, # 【修正】
        "tools_used": tools_used,
        "fallback_reason": fallback_reason_str,  # 【修正】maps_routes_failed / ranker_failed / vertex_llm_failed を明示
        "fallback_details": fallback_details,  # 【追加】UI表示用の詳細情報
        "route_quality": route_quality,
    }
    if req.debug:
        meta["plan"] = plan_steps
        meta["retry_policy"] = retry_policy
        # routes / places / ranker の内訳を追加
        meta["debug"] = {
            "routes": {
                "candidates_count": len(candidates),
                "candidates": [
                    {
                        "route_id": c.get("route_id"),
                        "distance_km": c.get("distance_km"),
                        "duration_min": c.get("duration_min"),
                    }
                    for c in candidates[:5]
                ],
                "chosen_route_id": chosen.get("route_id"),
            },
            "places": {
                "spots_count": len(spots),
                "spots": [{"name": s.name, "type": s.type} for s in spots] if spots else [],
            },
            "ranker": {
                "scores_count": len(score_map),
                "scores": [
                    {"route_id": route_id, "score": score}
                    for route_id, score in sorted(score_map.items(), key=lambda x: x[1], reverse=True)
                ],
            },
        }

    return GenerateRouteResponse(
        request_id=req.request_id,
        route={
            "route_id": chosen.get("route_id"),
            "polyline": chosen.get("polyline", "xxxx"),
            "distance_km": float(chosen.get("distance_km", req.distance_km)),
            "duration_min": int(chosen.get("duration_min") or 32),
            "summary": summary,
            "spots": spots,
        },
        meta=meta,
    )