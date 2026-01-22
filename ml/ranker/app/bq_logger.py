from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from google.cloud import bigquery

from app.settings import settings


class BigQueryRankResultLogger:
    """rank_result へのログ書き込み（失敗しても例外は上げない）"""

    def __init__(
        self,
        project: Optional[str] = None,
        dataset: Optional[str] = None,
        table: Optional[str] = None,
    ) -> None:
        self._project = project or settings.BQ_PROJECT
        self._dataset = dataset or settings.BQ_DATASET
        self._table = table or settings.BQ_RANK_RESULT_TABLE
        self._client = bigquery.Client(project=self._project) if self._project else bigquery.Client()

    def log_rank_result(self, rows: Iterable[Dict[str, Any]]) -> None:
        table_id = f"{self._client.project}.{self._dataset}.{self._table}"
        errors = self._client.insert_rows_json(table_id, list(rows))
        if errors:
            raise RuntimeError(f"BigQuery insert error: {errors}")

    @staticmethod
    def build_rows(
        request_id: str,
        items: Iterable[Dict[str, Any]],
        rule_version: str,
        model_version: str,
        status: str,
    ) -> List[Dict[str, Any]]:
        created_at = datetime.now(timezone.utc).isoformat()
        rows: List[Dict[str, Any]] = []
        for item in items:
            rows.append(
                {
                    "request_id": request_id,
                    "created_at": created_at,
                    "rule_version": rule_version,
                    "model_version": model_version,
                    "route_id": item["route_id"],
                    "rule_score": item["rule_score"],
                    "model_score": item.get("model_score"),
                    "model_latency_ms": item.get("model_latency_ms", 0),
                    "status": item.get("status") or status,
                }
            )
        return rows
