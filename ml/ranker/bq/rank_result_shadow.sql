-- rank_result テーブルDDL（シャドウ推論ログ用）
-- 実行例:
--   bq query --use_legacy_sql=false < rank_result_shadow.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE TABLE IF NOT EXISTS `firstdown_mvp.rank_result` (
  request_id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  rule_version STRING NOT NULL,
  model_version STRING NOT NULL,
  route_id STRING NOT NULL,
  rule_score FLOAT64,
  model_score FLOAT64,
  model_latency_ms INT64,
  status STRING
)
PARTITION BY DATE(created_at)
CLUSTER BY request_id, route_id, model_version;
