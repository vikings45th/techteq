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
    """
    テーマごとの簡潔な紹介文を返すフォールバック関数。
    """
    # テーマごとの簡潔な紹介文（定型文ではなく、自然な表現）
    theme_summaries = {
        "think": f"信号が少なく一定のリズムで歩ける約{distance_km:.1f}kmのルート。頭の中を整理するのに最適です。",
        "exercise": f"坂道や階段を多く含む約{distance_km:.1f}kmのルート。心拍数を上げてしっかり汗をかきましょう。",
        "refresh": f"賑やかな通りを歩く約{distance_km:.1f}kmのルート。エネルギーをチャージして気分転換できます。",
        "nature": f"緑豊かな公園をゆっくり抜ける約{distance_km:.1f}kmのルート。都会の喧騒から離れてリフレッシュできます。",
    }
    
    return theme_summaries.get(theme, f"約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける散歩コースです。")


def _theme_to_natural(theme: str) -> str:
    """Convert theme code to natural Japanese description."""
    theme_map = {
        "exercise": "運動やエクササイズ",
        "think": "思考やリフレッシュ",
        "refresh": "気分転換やリフレッシュ",
        "nature": "自然や緑",
    }
    return theme_map.get(theme, theme)


def _build_prompt(theme: str, distance_km: float, duration_min: float, spots: Optional[list], *, strict: bool) -> str:
    """
    テーマごとの雰囲気を伝えるプロンプトを生成。
    """
    # テーマごとの雰囲気・特徴の説明
    theme_descriptions = {
        "think": "思考や頭の整理に適した、信号が少なく一定のリズムで歩けるルート（例：川沿いの一本道など）。",
        "exercise": "運動やエクササイズに適した、坂道や階段を多く含む心拍数を上げるルート。",
        "refresh": "気分転換やリフレッシュに適した、賑やかな通りやお店が並ぶルート。",
        "nature": "自然や緑を楽しむ、都会の喧騒から離れた公園や緑豊かなルート。",
    }
    
    theme_desc = theme_descriptions.get(theme, f"約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける散歩コース。")

    if strict:
        # リトライ時：簡潔に
        return (
            f"散歩ルートの紹介文を日本語で1文だけ（60文字前後）作成してください。"
            f"テーマの雰囲気を反映しつつ、自然で読みやすい文章にしてください。必ず句点「。」で終える。"
            f" テーマ: {theme_desc}"
            f" 距離: 約{distance_km:.1f}km。所要時間: 約{duration_min:.0f}分。"
        )

    # 通常時：自然な文章で
    return (
        f"散歩ルートの紹介文を日本語で1文だけ（40〜70文字程度）作成してください。"
        f"テーマの雰囲気や特徴を自然に反映し、読みやすく簡潔な文章にしてください。必ず句点「。」で終える。"
        f" テーマ: {theme_desc}"
        f" 距離: 約{distance_km:.1f}km。所要時間: 約{duration_min:.0f}分。"
    )


def _build_config(*, temperature: float, max_output_tokens: int) -> types.GenerateContentConfig:
    top_p = float(getattr(settings, "VERTEX_TOP_P", 0.95))
    top_k = int(getattr(settings, "VERTEX_TOP_K", 40))

    return types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        top_p=top_p,
        top_k=top_k,
        # thinking_config は thinking_budget パラメータをサポートしていないため削除
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
                max_output_tokens=max(max_out, 1024), # 上限増（ログで561トークン必要だったため）
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
