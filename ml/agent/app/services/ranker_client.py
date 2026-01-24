from typing import Any, Dict, List, Tuple
import logging
import httpx

from app.settings import settings
from app.services.http_client import get_client

logger = logging.getLogger(__name__)


async def rank_routes(
    request_id: str,
    routes: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    内部Ranker APIを呼び出してルートをスコアリングする
    
    部分的な成功を許可（一部のルートが失敗してもOK）
    
    Args:
        request_id: リクエストID
        routes: ルートのリスト [{"route_id": "...", "features": {...}}, ...]
    
    Returns:
        (スコアリスト, 失敗したルートIDのリスト) のタプル
    """
    payload = {"request_id": request_id, "routes": routes}

    try:
        client = get_client()
        r = await client.post(
            f"{settings.RANKER_URL}/rank",
            json=payload,
            timeout=httpx.Timeout(settings.RANKER_TIMEOUT_SEC),
        )
    except httpx.TimeoutException as e:
        # タイムアウトエラー
        logger.error(
            "[Ranker Timeout] request_id=%s timeout_sec=%.1f err=%r",
            request_id,
            settings.RANKER_TIMEOUT_SEC,
            e,
        )
        raise
    except httpx.RequestError as e:
        # リクエストエラー（ネットワークエラーなど）
        logger.error("[Ranker Request Error] request_id=%s err=%r", request_id, e)
        raise

    if r.status_code == 200:
        # 成功: スコアと失敗したルートIDを返す
        data = r.json()
        return data.get("scores", []), data.get("failed_route_ids", [])
    if r.status_code != 200:
        # 200以外のステータスコード
        logger.warning(
            "[Ranker HTTP] request_id=%s status=%d body=%s",
            request_id,
            r.status_code,
            r.text[:500],
        )
    if r.status_code == 422:
        # 422エラー: Rankerがどのルートもスコアリングできなかった
        return [], [x.get("route_id") for x in routes if "route_id" in x]
    r.raise_for_status()  # その他のエラーは例外を発生
    return [], []
