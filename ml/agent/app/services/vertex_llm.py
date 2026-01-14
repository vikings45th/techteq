# vertex_llm.py
from __future__ import annotations

from typing import Optional, Any, Dict
import asyncio
import time
import logging

from google import genai
from google.genai import types

from app.settings import settings

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None


def _get_client() -> Optional[genai.Client]:
    global _client
    if not settings.VERTEX_PROJECT or not settings.VERTEX_LOCATION:
        return None
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.VERTEX_PROJECT,
            location=settings.VERTEX_LOCATION,
        )
    return _client


def _extract_text(resp: Any) -> str:
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

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
    meta: Dict[str, Any] = {}
    meta["usage_metadata"] = getattr(resp, "usage_metadata", None)

    candidates = getattr(resp, "candidates", None)
    if candidates:
        c0 = candidates[0]
        meta["finish_reason"] = getattr(c0, "finish_reason", None)
        meta["safety_ratings"] = getattr(c0, "safety_ratings", None)

        content = getattr(c0, "content", None)
        parts = getattr(content, "parts", None) if content else None
        meta["has_parts"] = bool(parts)
    else:
        meta["has_parts"] = False

    return meta


def _debug_dump(resp: Any) -> str:
    try:
        s = str(resp)
        return s[:800]
    except Exception:
        return "<unprintable>"


def _fallback_summary(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    spots_text = ""
    if spots:
        names = ", ".join(
            s.get("name") for s in spots if isinstance(s, dict) and s.get("name")
        )
        if names:
            spots_text = f"（見どころ: {names}）"
    return f"{theme}を楽しみながら約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける、気軽な散歩コースです{spots_text}。"


def _build_prompt(theme: str, distance_km: float, duration_min: float, spots: Optional[list], *, strict: bool) -> str:
    spots_text = ""
    if spots:
        names = ", ".join(
            s.get("name") for s in spots if isinstance(s, dict) and s.get("name")
        )
        if names:
            spots_text = f" 見どころ: {names}。"

    if strict:
        # リトライ時：短く・強制
        return (
            "次の情報から、日本語で1文だけ（60文字前後）紹介文を作成してください。"
            "余計な説明は不要。必ず句点「。」で終える。"
            f" テーマ:{theme} 距離:{distance_km:.1f}km 時間:{duration_min:.0f}分。"
            f"{spots_text}"
        )

    # 通常時
    return (
        "以下の散歩ルートの紹介文を日本語で1文だけ作成してください。"
        "（40〜70文字程度、丁寧で簡潔、句点「。」で終える）"
        f" テーマ: {theme}。目安距離: {distance_km:.1f}km。"
        f" 所要時間: {duration_min:.0f}分。"
        f"{spots_text}"
    )


def _build_config(*, temperature: float, max_output_tokens: int) -> types.GenerateContentConfig:
    top_p = float(getattr(settings, "VERTEX_TOP_P", 0.95))
    top_k = int(getattr(settings, "VERTEX_TOP_K", 40))

    return types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        top_p=top_p,
        top_k=top_k,
        thinking_config=types.ThinkingConfig(thinking_budget=0),  # thinking OFF
    )


async def _call_genai(client: genai.Client, model: str, prompt: str, cfg: types.GenerateContentConfig) -> Any:
    return await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt,
        config=cfg,
    )


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

    # 通常設定
    temperature = float(getattr(settings, "VERTEX_TEMPERATURE", 0.3))
    max_out = int(float(getattr(settings, "VERTEX_MAX_OUTPUT_TOKENS", 256)))

    # 1回目
    prompt = _build_prompt(theme, distance_km, duration_min, spots, strict=False)
    cfg = _build_config(temperature=temperature, max_output_tokens=max_out)

    top_p = float(getattr(settings, "VERTEX_TOP_P", 0.95))
    top_k = int(getattr(settings, "VERTEX_TOP_K", 40))
    logger.info(
        "[GenAI SDK Call] model=%s temp=%.2f max_out=%d top_p=%.2f top_k=%d",
        model_name, temperature, max_out, top_p, top_k
    )

    t0 = time.time()
    try:
        resp = await _call_genai(client, model_name, prompt, cfg)
        text = _extract_text(resp)
        meta = _safe_meta(resp)

        dt = int((time.time() - t0) * 1000)
        logger.info("[GenAI SDK Done] elapsed_ms=%s text_len=%s meta=%s", dt, len(text) if text else 0, meta)

        if text:
            return text

        # 空で、かつ MAX_TOKENS のときだけリトライ
        if str(meta.get("finish_reason")) == "FinishReason.MAX_TOKENS" or meta.get("finish_reason") == "MAX_TOKENS":
            logger.warning("[GenAI SDK Empty/MAX_TOKENS] retrying once. meta=%s resp=%s", meta, _debug_dump(resp))

            retry_prompt = _build_prompt(theme, distance_km, duration_min, spots, strict=True)
            retry_cfg = _build_config(
                temperature=min(temperature, 0.2),   # ブレ抑制
                max_output_tokens=max(max_out, 512), # 上限増
            )
            resp2 = await _call_genai(client, model_name, retry_prompt, retry_cfg)
            text2 = _extract_text(resp2)
            meta2 = _safe_meta(resp2)

            dt2 = int((time.time() - t0) * 1000)
            logger.info("[GenAI SDK Retry Done] elapsed_ms=%s text_len=%s meta=%s", dt2, len(text2) if text2 else 0, meta2)

            if text2:
                return text2

            logger.warning("[GenAI SDK Retry Empty] meta=%s resp=%s", meta2, _debug_dump(resp2))

        # それ以外の空はフォールバック
        return _fallback_summary(theme, distance_km, duration_min, spots)

    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        logger.exception("[GenAI SDK Error] elapsed_ms=%s err=%r", dt, e)
        return _fallback_summary(theme, distance_km, duration_min, spots)
