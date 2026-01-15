-- 学習開始ゲート判定用SQL
-- 実行例:
--   bq query --use_legacy_sql=false < training_gate.sql
-- ※ データセット名を変更する場合は下記のテーブル参照を修正してください。

WITH stats AS (
  SELECT
    (SELECT COUNT(*) FROM `firstdown_mvp.route_feedback`) AS feedback_count,
    (SELECT COUNT(*) FROM `firstdown_mvp.training_view` WHERE label IS NOT NULL) AS labeled_count
)
SELECT
  feedback_count,
  labeled_count,
  feedback_count >= 1000 AS feedback_ready,
  labeled_count >= 1000 AS labeled_ready,
  (feedback_count >= 1000 AND labeled_count >= 1000) AS training_ready
FROM stats;
