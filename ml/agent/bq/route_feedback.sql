-- route_feedback テーブルDDL
-- 実行例:
--   bq query --use_legacy_sql=false < route_feedback.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE TABLE IF NOT EXISTS `firstdown_mvp.route_feedback` (
  event_ts TIMESTAMP,
  request_id STRING,
  route_id STRING,
  rating INT64,
  note STRING
);
