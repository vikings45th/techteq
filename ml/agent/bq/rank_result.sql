-- rank_result テーブルDDL
-- 実行例:
--   bq query --use_legacy_sql=false < rank_result.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE TABLE IF NOT EXISTS `firstdown_mvp.rank_result` (
  event_ts TIMESTAMP NOT NULL,
  request_id STRING NOT NULL,
  route_id STRING NOT NULL,

  score FLOAT64,           -- success=true のときのみ
  success BOOL NOT NULL,
  error_reason STRING,

  model_version STRING NOT NULL, -- endpoint_id等
  latency_ms INT64 NOT NULL
)
PARTITION BY DATE(event_ts)
CLUSTER BY request_id, route_id, model_version;
