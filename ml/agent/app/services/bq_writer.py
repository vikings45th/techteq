from __future__ import annotations
from typing import Any, Dict, Iterable, Optional
from google.cloud import bigquery

from app.settings import settings


_client: Optional[bigquery.Client] = None  # BigQueryクライアントのシングルトン


def _bq() -> bigquery.Client:
    """
    BigQueryクライアントを取得（シングルトンパターン）
    
    Returns:
        BigQueryクライアントインスタンス
    """
    global _client
    if _client is None:
        _client = bigquery.Client()
    return _client


def insert_rows(table: str, rows: Iterable[Dict[str, Any]]) -> None:
    """
    BigQueryにデータを挿入する（ベストエフォート方式）
    
    失敗してもユーザーフローを中断しない。MVPではエラーを無視する。
    
    Args:
        table: テーブル名（データセット名は除く、例: "route_request"）
        rows: 挿入する行のイテレータ（辞書のリスト）
    """
    rows = list(rows)
    if not rows:
        return
    # テーブルIDを構築: project.dataset.table
    table_id = f"{_bq().project}.{settings.BQ_DATASET}.{table}"
    errors = _bq().insert_rows_json(table_id, rows)
    # ベストエフォート: MVPではエラーを無視（必要に応じてログ出力可能）
    if errors:
        # ここで構造化ログを出力可能
        pass
