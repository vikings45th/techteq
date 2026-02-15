from __future__ import annotations
import time
import logging
from typing import Dict
from contextlib import asynccontextmanager
import httpx

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from app.schemas import (
    GenerateRouteRequest,
    GenerateRouteResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from app.settings import settings
from app.services import http_client
from app.services import bq_writer
from app.services.ttl_cache import (
    build_cache_key,
    cache_get,
    cache_key_prefix,
    cache_set,
    _get_key_lock,
)
from app.graph import get_route_graph_mermaid, run_generate_graph


def _configure_logging() -> None:
    level = str(getattr(settings, "LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(message)s",
        force=True,
    )


_configure_logging()
@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(settings.REQUEST_TIMEOUT_SEC)
    limits = httpx.Limits(max_connections=50, max_keepalive_connections=10)
    client = httpx.AsyncClient(timeout=timeout, limits=limits)
    http_client.set_client(client)
    yield
    await client.aclose()
    http_client.set_client(None)


app = FastAPI(title="firstdown Agent API", version="1.0.0", lifespan=lifespan)

logger = logging.getLogger(__name__)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/route/graph", response_class=PlainTextResponse)
def get_route_graph() -> str:
    return get_route_graph_mermaid()


@app.post("/route/feedback", response_model=FeedbackResponse)
def post_feedback(req: FeedbackRequest) -> FeedbackResponse:
    # Best-effort store
    bq_writer.insert_rows(settings.BQ_TABLE_FEEDBACK, [{
        "event_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": req.request_id,
        "route_id": req.route_id,
        "rating": int(req.rating),
        "note": None,
    }])
    return FeedbackResponse(request_id=req.request_id)


@app.post("/route/generate", response_model=GenerateRouteResponse)
async def generate(req: GenerateRouteRequest) -> GenerateRouteResponse:
    # debug 時はキャッシュを使わず毎回生成（レスポンスメタに影響しうるため）
    if req.debug:
        logger.info("cache_bypass debug=true request_id=%s", req.request_id)
        return await run_generate_graph(req)

    if not settings.GENERATE_CACHE_ENABLED:
        return await run_generate_graph(req)

    key = build_cache_key(req)
    key_pre = cache_key_prefix(key)

    # 1) キャッシュ参照
    cached = cache_get(key)
    if cached is not None:
        resp = GenerateRouteResponse(**cached)
        resp.request_id = req.request_id
        logger.info("cache_hit generate key=%s req=%s", key_pre, req.request_id)
        return resp

    logger.info("cache_miss generate key=%s req=%s", key_pre, req.request_id)

    # 2) 同一キーの並行リクエストを1本に集約（スタンピード防止）
    key_lock = await _get_key_lock(key)
    async with key_lock:
        # 二重チェック（ロック取得中に他リクエストがキャッシュした可能性）
        cached = cache_get(key)
        if cached is not None:
            resp = GenerateRouteResponse(**cached)
            resp.request_id = req.request_id
            logger.info("cache_hit generate key=%s req=%s (after lock)", key_pre, req.request_id)
            return resp

        # 3) 生成実行（エラー時はキャッシュせず例外はそのまま伝播）
        response = await run_generate_graph(req)
        cache_set(key, response.model_dump())
        return response
