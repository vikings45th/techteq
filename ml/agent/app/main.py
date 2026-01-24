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
from app.graph import get_route_graph_mermaid, run_generate_graph

def _configure_logging() -> None:
    level = str(getattr(settings, "LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO))


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
    return await run_generate_graph(req)
