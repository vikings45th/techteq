from __future__ import annotations

import asyncio
import json
import random
import re
from pathlib import Path
from typing import Optional
import logging

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pydantic import ValidationError

import vertexai
from google.api_core.exceptions import (
    InvalidArgument,
    NotFound,
    PermissionDenied,
    ResourceExhausted,
    ServiceUnavailable,
)
from vertexai.generative_models import GenerationConfig, GenerativeModel

from app.schemas import DescriptionResponse, TitleResponse, TitleDescriptionResponse
from app.settings import settings

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_ENV = Environment(
    loader=FileSystemLoader(str(_PROMPT_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)

# Vertex AI 初期化は初回のみ
_VERTEX_INIT_DONE = False
# モデルは model_name のみでキャッシュ（GenerationConfig は呼び出しごとに渡す）
_VERTEX_MODEL_CACHE: dict[str, GenerativeModel] = {}

# 空レスポンスログ用
_RAW_RESPONSE_LOG_CAP = 2000


def _ensure_vertex_init() -> None:
    global _VERTEX_INIT_DONE
    if _VERTEX_INIT_DONE:
        return
    if not settings.VERTEX_PROJECT or not settings.VERTEX_LOCATION:
        return
    vertexai.init(project=settings.VERTEX_PROJECT, location=settings.VERTEX_LOCATION)
    _VERTEX_INIT_DONE = True


def _get_vertex_model(model_name: str) -> Optional[GenerativeModel]:
    if not model_name or not settings.VERTEX_PROJECT or not settings.VERTEX_LOCATION:
        return None
    _ensure_vertex_init()
    if model_name in _VERTEX_MODEL_CACHE:
        return _VERTEX_MODEL_CACHE[model_name]
    model = GenerativeModel(model_name)
    _VERTEX_MODEL_CACHE[model_name] = model
    return model


def _extract_text_from_response(resp: object) -> str:
    """Vertex AI GenerateContentResponse からテキストを安全に抽出する。"""
    if resp is None:
        return ""
    # 1) .text プロパティ（SDK が提供する場合）
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    # 2) candidates[0].content.parts[0].text
    candidates = getattr(resp, "candidates", None)
    if not candidates or not isinstance(candidates, (list, tuple)):
        return ""
    first = candidates[0] if candidates else None
    if first is None:
        return ""
    content = getattr(first, "content", None)
    if content is None:
        return ""
    parts = getattr(content, "parts", None)
    if not parts or not isinstance(parts, (list, tuple)):
        return ""
    part = parts[0] if parts else None
    if part is None:
        return ""
    t = getattr(part, "text", None)
    if isinstance(t, str) and t.strip():
        return t.strip()
    return ""


def _log_raw_response(raw: object) -> None:
    """空判定時に Vertex レスポンスをログ出しし、原因切り分けする。"""
    cap = _RAW_RESPONSE_LOG_CAP
    ty = type(raw).__name__
    logger.warning("[Vertex LLM] raw response type=%s", ty)
    logger.warning("[Vertex LLM] raw repr=%s", repr(raw)[:cap])
    if raw is None:
        return
    if hasattr(raw, "candidates"):
        cands = getattr(raw, "candidates", None)
        logger.warning("[Vertex LLM] raw.candidates len=%s", len(cands) if cands else 0)
        if cands:
            logger.warning("[Vertex LLM] raw.candidates[0]=%s", repr(cands[0])[:cap])
    if hasattr(raw, "prompt_feedback"):
        pf = getattr(raw, "prompt_feedback", None)
        if pf is not None:
            logger.warning("[Vertex LLM] raw.prompt_feedback=%s", repr(pf)[:cap])


def _invoke_vertex_text_sync(
    prompt: str,
    *,
    temperature: float,
    max_output_tokens: int,
) -> tuple[str, bool]:
    """
    Vertex AI 公式 SDK で同期的にテキスト生成する。
    戻り値: (抽出したテキスト, リトライすべきか).
    - 成功: (text, False)
    - 恒久エラー(404/403/InvalidArgument) or 空レスポンス: ("", False)
    - 一時的エラー(429/503): ("", True)
    """
    model_name = settings.VERTEX_TEXT_MODEL
    model = _get_vertex_model(model_name or "")
    if model is None:
        logger.warning("[Vertex LLM] Vertex not configured (project/location/model)")
        return ("", False)

    top_p = float(getattr(settings, "VERTEX_TOP_P", 0.95))
    top_k = int(getattr(settings, "VERTEX_TOP_K", 40))
    config = GenerationConfig(
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
    )
    try:
        resp = model.generate_content(prompt, generation_config=config)
    except NotFound:
        logger.warning("[Vertex LLM] NotFound (404), skip retry")
        return ("", False)
    except PermissionDenied:
        logger.warning("[Vertex LLM] PermissionDenied (403), skip retry")
        return ("", False)
    except InvalidArgument as e:
        logger.warning("[Vertex LLM] InvalidArgument, skip retry: %r", e)
        return ("", False)
    except ResourceExhausted as e:
        logger.warning("[Vertex LLM] ResourceExhausted (429), retryable: %r", e)
        return ("", True)
    except ServiceUnavailable as e:
        logger.warning("[Vertex LLM] ServiceUnavailable (503), retryable: %r", e)
        return ("", True)
    except Exception as e:
        logger.exception("[Vertex LLM] unexpected error: %r", e)
        return ("", False)

    text = _extract_text_from_response(resp)
    if not text:
        _log_raw_response(resp)
        logger.warning("[Vertex LLM] empty response (vertex SDK)")
        return ("", False)
    return (text, False)


async def _invoke_vertex_text(
    prompt: str,
    *,
    temperature: float,
    max_output_tokens: int,
) -> str:
    """
    Vertex AI 公式 SDK でテキスト生成（非同期ラップ）。
    429/503 は最大1回だけ短いバックオフでリトライする。
    """
    loop = asyncio.get_event_loop()
    text, should_retry = await loop.run_in_executor(
        None,
        lambda: _invoke_vertex_text_sync(
            prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    if not should_retry:
        return text
    # 0.3〜1.0秒のバックオフで1回だけリトライ
    backoff = 0.3 + (random.random() * 0.7)
    logger.info("[Vertex LLM] retry after %.2fs (429/503)", backoff)
    await asyncio.sleep(backoff)
    text2, _ = await loop.run_in_executor(
        None,
        lambda: _invoke_vertex_text_sync(
            prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    return text2


def _forbidden_words() -> list[str]:
    raw = str(getattr(settings, "VERTEX_FORBIDDEN_WORDS", "") or "")
    return [w.strip() for w in raw.split(",") if w.strip()]


def _contains_forbidden(text: str, forbidden_words: list[str]) -> Optional[str]:
    for w in forbidden_words:
        if w in text:
            return w
    return None


def _render_prompt(template_name: str, **context: object) -> str:
    try:
        template = _PROMPT_ENV.get_template(template_name)
    except TemplateNotFound:
        logger.error("[Vertex LLM] template not found: %s", template_name)
        return ""
    return template.render(**context).strip()


def _coerce_structured(result: object, schema: type) -> object:
    if isinstance(result, schema):
        return result
    if isinstance(result, dict):
        return schema.model_validate(result)
    if isinstance(result, str):
        text = result.strip()
        if not text:
            raise ValueError("empty string cannot be parsed as structured response")
        try:
            return schema.model_validate(json.loads(text))
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return schema.model_validate(json.loads(match.group(0)))
    return schema.model_validate(result)


def _spot_names(spots: Optional[list]) -> list[str]:
    if not spots:
        return []
    names: list[str] = []
    for s in spots:
        name = None
        if isinstance(s, dict):
            name = s.get("name")
        else:
            name = getattr(s, "name", None)
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _fallback_summary(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    theme_summaries = {
        "think": [
            f"静かなリズムで歩ける約{distance_km:.1f}kmのルートです。頭がすっと整う、優しいひとときを過ごしてみませんか。",
            f"約{distance_km:.1f}kmの落ち着いた道のりです。ゆっくり歩きながら、少しずつ心が軽くなっていくかもしれません。",
            f"約{distance_km:.1f}kmの静かな散歩道です。自分のペースで、無理せず歩いてみてください。",
        ],
        "exercise": [
            f"アップダウンもある約{distance_km:.1f}kmのルートです。ちょっと勇気を出して、体を動かしてみませんか。",
            f"約{distance_km:.1f}kmの道のりです。少し体を動かすことで、気持ちも少しずつ前を向けるかもしれません。",
            f"約{distance_km:.1f}kmのルートです。無理せず、自分のペースで歩いてみてください。",
        ],
        "refresh": [
            f"街の景色を感じながら歩ける約{distance_km:.1f}kmのルートです。外に出てみることで、少し気持ちが変わるかもしれません。",
            f"約{distance_km:.1f}kmの街歩きです。景色の変化を感じながら、ゆっくり歩いてみませんか。",
            f"にぎわいを感じる約{distance_km:.1f}kmの道のりです。心が少しずつ軽くなる時間を過ごしてみてください。",
        ],
        "nature": [
            f"緑に包まれながら歩ける約{distance_km:.1f}kmのルートです。自然の中で、ゆっくりと心を休めてみませんか。",
            f"約{distance_km:.1f}kmの自然を感じる散歩道です。深呼吸しながら、優しい景色に包まれてみてください。",
            f"木漏れ日を感じる約{distance_km:.1f}kmのルートです。癒やしの時間を、無理せず過ごしてみてください。",
        ],
    }
    options = theme_summaries.get(
        theme,
        [f"約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける散歩コースです。少しずつ、歩いてみませんか。"],
    )
    return random.choice(options)


def _fallback_title(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    theme_titles = {
        "think": ["静けさの川沿い", "ひと息つける小道", "優しい並木道"],
        "exercise": ["ゆっくり歩ける坂道", "無理しない散歩道", "自分のペースで歩く道"],
        "refresh": ["街なか散歩", "優しい街歩き", "気分転換の小径"],
        "nature": ["木漏れ日の森歩き", "緑に包まれる道", "自然に寄り添う散策"],
    }
    base = random.choice(theme_titles.get(theme, ["散歩"]))
    return f"{base}コース"


def fallback_title(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    return _fallback_title(theme, distance_km, duration_min, spots)


def _theme_to_natural(theme: str) -> str:
    theme_map = {
        "think": "考えなくていい道モード。今日は、頭を休ませる道を用意しました。一本道が中心のコースです。考えなくてOK。歩くだけで大丈夫です。",
        "nature": "呼吸を整えるモード。呼吸が少し楽になる道です。空や木が見える場所を通ります。何かしなくていいので、ただ外の空気に触れてみませんか。",
        "refresh": "ちょっと気分転換モード。景色を少しだけ変える散歩です。見るだけの場所がいくつかあります。寄らなくて大丈夫。通り過ぎるだけでOKです。",
        "exercise": "体を使って整えるモード。少し体を動かすと、気持ちが変わることがあります。ゆるい坂があるコースです。途中でやめてもOK。行けたところまでで十分です。",
    }
    return theme_map.get(theme, theme)


async def generate_summary(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> Optional[str]:
    temperature = float(getattr(settings, "VERTEX_TEMPERATURE", 0.3))
    max_out = int(float(getattr(settings, "VERTEX_MAX_OUTPUT_TOKENS", 256)))
    forbidden_words = _forbidden_words()

    theme_desc = _theme_to_natural(theme)
    names = _spot_names(spots)
    spots_text = "、".join(names[:4]) if names else ""

    attempts = [
        {"strict": False, "min_chars": 80, "max_chars": 120, "temperature": temperature, "max_out": max_out},
        {"strict": True, "min_chars": 90, "max_chars": 120, "temperature": min(temperature, 0.2), "max_out": max(max_out, 192)},
    ]

    for attempt in attempts:
        prompt = _render_prompt(
            "description.jinja",
            strict=attempt["strict"],
            min_chars=attempt["min_chars"],
            max_chars=attempt["max_chars"],
            theme_desc=theme_desc,
            distance_km_str=f"{distance_km:.1f}km",
            duration_min_str=f"{duration_min:.0f}分",
            spots_text=spots_text,
            forbidden_words=forbidden_words,
        )
        try:
            logger.info(
                "[Vertex LLM Summary] invoke max_output_tokens=%s temperature=%s",
                attempt["max_out"],
                attempt["temperature"],
            )
            text = await _invoke_vertex_text(
                prompt,
                temperature=attempt["temperature"],
                max_output_tokens=attempt["max_out"],
            )
            if not text:
                continue
            parsed = _coerce_structured(text, DescriptionResponse)
            desc_text = parsed.description
            banned = _contains_forbidden(desc_text, forbidden_words)
            if banned:
                raise ValueError(f"forbidden word found: {banned}")
            return desc_text
        except (ValidationError, ValueError) as e:
            logger.warning("[Vertex LLM Summary Invalid] err=%r", e)
        except Exception as e:
            logger.exception("[Vertex LLM Summary Error] err=%r", e)

    return _fallback_summary(theme, distance_km, duration_min, spots)


async def generate_title(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> Optional[str]:
    temperature = float(getattr(settings, "VERTEX_TEMPERATURE", 0.3))
    max_out = int(float(getattr(settings, "VERTEX_MAX_OUTPUT_TOKENS", 64)))
    forbidden_words = _forbidden_words()

    theme_desc = _theme_to_natural(theme)

    attempts = [
        {"strict": False, "min_chars": 8, "max_chars": 20, "temperature": min(temperature + 0.1, 0.6), "max_out": max_out},
        {"strict": True, "min_chars": 8, "max_chars": 18, "temperature": min(temperature, 0.2), "max_out": max(max_out, 96)},
    ]

    for attempt in attempts:
        prompt = _render_prompt(
            "title.jinja",
            strict=attempt["strict"],
            min_chars=attempt["min_chars"],
            max_chars=attempt["max_chars"],
            theme_desc=theme_desc,
            distance_km_str=f"{distance_km:.1f}km",
            duration_min_str=f"{duration_min:.0f}分",
            forbidden_words=forbidden_words,
        )
        try:
            logger.info(
                "[Vertex LLM Title] invoke max_output_tokens=%s temperature=%s",
                attempt["max_out"],
                attempt["temperature"],
            )
            text = await _invoke_vertex_text(
                prompt,
                temperature=attempt["temperature"],
                max_output_tokens=attempt["max_out"],
            )
            if not text:
                continue
            parsed = _coerce_structured(text, TitleResponse)
            title_text = parsed.title
            banned = _contains_forbidden(title_text, forbidden_words)
            if banned:
                raise ValueError(f"forbidden word found: {banned}")
            return title_text
        except (ValidationError, ValueError) as e:
            logger.warning("[Vertex LLM Title Invalid] err=%r", e)
        except Exception as e:
            logger.exception("[Vertex LLM Title Error] err=%r", e)

    return _fallback_title(theme, distance_km, duration_min, spots)


async def generate_title_and_description(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> dict[str, str]:
    temperature = float(getattr(settings, "VERTEX_TEMPERATURE", 0.3))
    max_out = int(float(getattr(settings, "VERTEX_MAX_OUTPUT_TOKENS", 256)))
    forbidden_words = _forbidden_words()

    theme_desc = _theme_to_natural(theme)
    names = _spot_names(spots)
    spots_text = "、".join(names[:4]) if names else ""

    attempts = [
        {
            "strict": False,
            "title_min": 8,
            "title_max": 20,
            "desc_min": 80,
            "desc_max": 120,
            "temperature": temperature,
            "max_out": max(max_out, 640),
        },
        {
            "strict": True,
            "title_min": 8,
            "title_max": 18,
            "desc_min": 90,
            "desc_max": 120,
            "temperature": min(temperature, 0.2),
            "max_out": max(max_out, 640),
        },
    ]

    for attempt in attempts:
        prompt = _render_prompt(
            "title_description.jinja",
            strict=attempt["strict"],
            title_min_chars=attempt["title_min"],
            title_max_chars=attempt["title_max"],
            desc_min_chars=attempt["desc_min"],
            desc_max_chars=attempt["desc_max"],
            theme_desc=theme_desc,
            distance_km_str=f"{distance_km:.1f}km",
            duration_min_str=f"{duration_min:.0f}分",
            spots_text=spots_text,
            forbidden_words=forbidden_words,
        )
        try:
            max_tokens = attempt["max_out"]
            logger.info(
                "[Vertex LLM Title+Summary] invoke max_output_tokens=%s temperature=%s",
                max_tokens,
                attempt["temperature"],
            )
            text = await _invoke_vertex_text(
                prompt,
                temperature=attempt["temperature"],
                max_output_tokens=max_tokens,
            )
            if not text:
                logger.warning("[Vertex LLM Title+Summary] empty response")
                continue
            parsed = _coerce_structured(text, TitleDescriptionResponse)
            title = parsed.title
            description = parsed.description
            banned = _contains_forbidden(title, forbidden_words) or _contains_forbidden(description, forbidden_words)
            if banned:
                raise ValueError(f"forbidden word found: {banned}")
            return {"title": title, "description": description}
        except (ValidationError, ValueError) as e:
            logger.warning("[Vertex LLM Title+Summary Invalid] err=%r", e)
        except Exception as e:
            logger.exception("[Vertex LLM Title+Summary Error] err=%r", e)

    return {
        "title": _fallback_title(theme, distance_km, duration_min, spots),
        "description": _fallback_summary(theme, distance_km, duration_min, spots),
    }
