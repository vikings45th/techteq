-- route_proposal テーブルDDL
-- 実行例:
--   bq query --use_legacy_sql=false < route_proposal.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE TABLE IF NOT EXISTS `firstdown_mvp.route_proposal` (
  event_ts TIMESTAMP,
  request_id STRING,
  chosen_route_id STRING,
  fallback_used BOOL,
  fallback_reason STRING,
  tools_used ARRAY<STRING>,
  summary_type STRING,
  total_latency_ms INT64,
  features_version STRING,
  ranker_version STRING
);
