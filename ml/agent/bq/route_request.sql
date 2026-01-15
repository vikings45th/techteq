-- route_request テーブルDDL
-- 実行例:
--   bq query --use_legacy_sql=false < route_request.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE TABLE IF NOT EXISTS `firstdown_mvp.route_request` (
  event_ts TIMESTAMP,
  request_id STRING,
  theme STRING,
  distance_km_target FLOAT64,
  start_lat FLOAT64,
  start_lng FLOAT64,
  round_trip BOOL,
  debug BOOL,
  client_version STRING,
  user_agent STRING,
  ip_hash STRING
);
