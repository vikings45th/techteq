-- route_candidate テーブルDDL
-- 実行例:
--   bq query --use_legacy_sql=false < route_candidate.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE TABLE IF NOT EXISTS `firstdown_mvp.route_candidate` (
  event_ts TIMESTAMP,
  event_id STRING,
  request_id STRING,
  route_id STRING,
  candidate_index INT64,
  theme STRING,
  round_trip BOOL,
  fallback BOOL,
  chosen_flag BOOL,
  shown_rank INT64,
  features_version STRING,
  ranker_version STRING,
  distance_km FLOAT64,
  duration_min FLOAT64,
  loop_closure_m FLOAT64,
  bbox_area FLOAT64,
  path_length_ratio FLOAT64,
  turn_count INT64,
  turn_density FLOAT64,
  theme_exercise INT64,
  theme_think INT64,
  theme_refresh INT64,
  theme_nature INT64,
  round_trip_req INT64,
  round_trip_fit INT64,
  distance_error_ratio FLOAT64,
  relaxation_step INT64,
  candidate_rank_in_theme INT64,
  has_stairs INT64,
  elevation_gain_m FLOAT64,
  elevation_density FLOAT64,
  poi_density FLOAT64,
  park_poi_ratio FLOAT64
);
