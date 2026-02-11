-- 学習用ビュー: route_candidate と route_feedback を結合
-- 弱い負例ルール:
--   - rating が 4〜5 のときのみ非採用候補に負例を付与
--   - 全非採用を負例にせず、上位K/ランダムKで抑制
-- 実行例:
--   bq query --use_legacy_sql=false < training_view.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE OR REPLACE VIEW `firstdown_mvp.training_view` AS
WITH feedback_high_raw AS (
  SELECT
    request_id,
    route_id,
    rating,
    event_ts
  FROM `firstdown_mvp.route_feedback`
  WHERE rating IN (4, 5)
    AND event_ts >= TIMESTAMP '2026-02-01'
),

-- 1 request に複数 feedback がある場合に備えて 1行へ正規化（最新を採用）
feedback_high AS (
  SELECT
    request_id,
    ARRAY_AGG(STRUCT(route_id, rating, event_ts) ORDER BY event_ts DESC LIMIT 1)[OFFSET(0)] AS fb
  FROM feedback_high_raw
  GROUP BY request_id
),

positives AS (
  SELECT
    c.*,
    fh.fb.rating  AS feedback_rating,
    fh.fb.event_ts AS feedback_ts,
    1 AS label,
    "positive" AS label_type,
    1.0 AS label_weight
  FROM `firstdown_mvp.route_candidate` AS c
  JOIN feedback_high AS fh
    ON c.request_id = fh.request_id
   AND c.route_id   = fh.fb.route_id
),

negatives_raw AS (
  SELECT
    c.*,
    fh.fb.rating  AS feedback_rating,
    fh.fb.event_ts AS feedback_ts
  FROM `firstdown_mvp.route_candidate` AS c
  JOIN feedback_high AS fh
    ON c.request_id = fh.request_id
  WHERE c.route_id != fh.fb.route_id
),

negatives_scored AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY request_id
      ORDER BY COALESCE(shown_rank, candidate_rank_in_theme, 999999) ASC
    ) AS rn_top,

    -- ビューでも再現できる「固定ランダム順」
    ROW_NUMBER() OVER (
      PARTITION BY request_id
      ORDER BY FARM_FINGERPRINT(CONCAT(request_id, ":", route_id)) ASC
    ) AS rn_rand
  FROM negatives_raw
),

negatives AS (
  SELECT
    *,
    0 AS label,
    "weak_negative" AS label_type,
    0.5 AS label_weight
  FROM negatives_scored
  WHERE rn_top <= 2 OR rn_rand <= 2
)

SELECT
  request_id,
  route_id,
  theme,
  round_trip,
  fallback,
  features_version,
  ranker_version,
  distance_km,
  duration_min,
  loop_closure_m,
  bbox_area,
  path_length_ratio,
  turn_count,
  turn_density,
  theme_exercise,
  theme_think,
  theme_refresh,
  theme_nature,
  round_trip_req,
  round_trip_fit,
  distance_error_ratio,
  relaxation_step,
  candidate_rank_in_theme,
  has_stairs,
  elevation_gain_m,
  elevation_density,
  poi_density,
  park_poi_ratio,
  feedback_rating,
  feedback_ts,
  label,
  label_type,
  label_weight
FROM positives

UNION ALL

SELECT
  request_id,
  route_id,
  theme,
  round_trip,
  fallback,
  features_version,
  ranker_version,
  distance_km,
  duration_min,
  loop_closure_m,
  bbox_area,
  path_length_ratio,
  turn_count,
  turn_density,
  theme_exercise,
  theme_think,
  theme_refresh,
  theme_nature,
  round_trip_req,
  round_trip_fit,
  distance_error_ratio,
  relaxation_step,
  candidate_rank_in_theme,
  has_stairs,
  elevation_gain_m,
  elevation_density,
  poi_density,
  park_poi_ratio,
  feedback_rating,
  feedback_ts,
  label,
  label_type,
  label_weight
FROM negatives;
