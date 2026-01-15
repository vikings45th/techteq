-- route_proposal_polyline テーブルDDL
-- 実行例:
--   bq query --use_legacy_sql=false < route_proposal_polyline.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

CREATE TABLE IF NOT EXISTS `firstdown_mvp.route_proposal_polyline` (
  event_ts TIMESTAMP NOT NULL,
  request_id STRING NOT NULL,
  chosen_route_id STRING NOT NULL,
  polyline STRING NOT NULL
)
PARTITION BY DATE(event_ts)
CLUSTER BY request_id, chosen_route_id;
