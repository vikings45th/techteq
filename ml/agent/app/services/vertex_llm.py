# vertex_llm.py
from __future__ import annotations

from typing import Optional, Any, Dict, Tuple
import asyncio
import time
import logging

from google import genai
from google.genai import types

from app.settings import settings

logger = logging.getLogger(__name__)

# Process-wide singleton (lazy init)
_client: Optional[genai.Client] = None


def _get_client() -> Optional[genai.Client]:
    """
    Google Gen AI SDK client configured for Vertex AI.
    Auth: ADC (Cloud Run default) or local gcloud auth application-default.
    """
    global _client

    project = settings.VERTEX_PROJECT
    location = settings.VERTEX_LOCATION
    if not project or not location:
        return None

    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
    return _client


def _extract_text(resp: Any) -> str:
    """
    Best-effort extraction of generated text.
    google-genai generally exposes resp.text, but keep defensive fallback.
    """
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    # fallback: try candidates/parts
    candidates = getattr(resp, "candidates", None)
    if candidates:
        c0 = candidates[0]
        content = getattr(c0, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts:
            out = []
            for p in parts:
                t = getattr(p, "text", None)
                if isinstance(t, str):
                    out.append(t)
            joined = "".join(out).strip()
            if joined:
                return joined

    return ""


def _safe_meta(resp: Any) -> Dict[str, Any]:
    """
    Collect debug-friendly metadata without assuming exact response shape.
    """
    meta: Dict[str, Any] = {}
    meta["usage_metadata"] = getattr(resp, "usage_metadata", None)

    candidates = getattr(resp, "candidates", None)
    if candidates:
        c0 = candidates[0]
        meta["finish_reason"] = getattr(c0, "finish_reason", None)
        meta["safety_ratings"] = getattr(c0, "safety_ratings", None)
    return meta


def _fallback_summary(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    spots_text = ""
    if spots:
        names = ", ".join(
            s.get("name")
            for s in spots
            if isinstance(s, dict) and s.get("name")
        )
        if names:
            spots_text = f"（見どころ: {names}）"
    return f"{theme}を楽しみながら約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける、気軽な散歩コースです{spots_text}。"


async def generate_summary(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> Optional[str]:
    """
    1文の散歩ルート紹介文を生成（Google Gen AI SDK / Vertex AI）。

    重要:
    - SDK は同期なので asyncio.to_thread() で呼び出す
    - 失敗/空ならフォールバック文を返してUXを安定化
    """
    model_name = settings.VERTEX_TEXT_MODEL
    if not model_name:
        return None

    client = _get_client()
    if client is None:
        return None

    # spots をプロンプトへ（任意）
    spots_text = ""
    if spots:
        names = ", ".join(
            s.get("name")
            for s in spots
            if isinstance(s, dict) and s.get("name")
        )
        if names:
            spots_text = f" 見どころ: {names}。"

    prompt = (
        "以下の散歩ルートの紹介文を日本語で1文だけ作成してください。"
        "（40〜70文字程度、丁寧で簡潔、句点「。」で終える）"
        f" テーマ: {theme}。目安距離: {distance_km:.1f}km。"
        f" 所要時間: {duration_min:.0f}分。"
        f"{spots_text}"
    )

    # Settings 反映（型が float でも int 化して吸収）
    temperature = float(getattr(settings, "VERTEX_TEMPERATURE", 0.3))
    max_output_tokens = int(float(getattr(settings, "VERTEX_MAX_OUTPUT_TOKENS", 256)))
    top_p = float(getattr(settings, "VERTEX_TOP_P", 0.95))
    top_k = int(getattr(settings, "VERTEX_TOP_K", 40))

    cfg = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        top_p=top_p,
        top_k=top_k,
        # thinking_config は thinking_budget パラメータをサポートしていないため削除
    )

    logger.info(
        "[GenAI SDK Call] model=%s temp=%.2f max_out=%d top_p=%.2f top_k=%d",
        model_name, temperature, max_output_tokens, top_p, top_k
    )

    t0 = time.time()
    try:
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=prompt,
            config=cfg,
        )
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        logger.exception("[GenAI SDK Error] elapsed_ms=%s err=%r", dt, e)
        return _fallback_summary(theme, distance_km, duration_min, spots)

    dt = int((time.time() - t0) * 1000)
    text = _extract_text(resp)
    meta = _safe_meta(resp)

    logger.info(
        "[GenAI SDK Done] elapsed_ms=%s text_len=%s meta=%s",
        dt,
        len(text) if text else 0,
        meta,
    )

    if text:
        return text

    logger.warning("[GenAI SDK Empty] meta=%s", meta)
    return _fallback_summary(theme, distance_km, duration_min, spots)
