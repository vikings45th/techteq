from __future__ import annotations

from pathlib import Path
import json
import random
import re
from typing import Optional
import logging

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from langchain_core.exceptions import OutputParserException
from langchain_google_vertexai import ChatVertexAI
from pydantic import ValidationError

from app.schemas import DescriptionResponse, TitleResponse, TitleDescriptionResponse
from app.settings import settings

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_ENV = Environment(
    loader=FileSystemLoader(str(_PROMPT_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)

_LLM_CACHE: dict[tuple[float, int], ChatVertexAI] = {}


def _get_llm(*, temperature: float, max_output_tokens: int) -> Optional[ChatVertexAI]:
    model_name = settings.VERTEX_TEXT_MODEL
    if not model_name or not settings.VERTEX_PROJECT or not settings.VERTEX_LOCATION:
        return None

    key = (temperature, max_output_tokens)
    if key in _LLM_CACHE:
        return _LLM_CACHE[key]

    llm = ChatVertexAI(
        project=settings.VERTEX_PROJECT,
        location=settings.VERTEX_LOCATION,
        model_name=model_name,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        top_p=float(getattr(settings, "VERTEX_TOP_P", 0.95)),
        top_k=int(getattr(settings, "VERTEX_TOP_K", 40)),
    )
    _LLM_CACHE[key] = llm
    return llm


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
            f"静かなリズムで歩ける約{distance_km:.1f}kmのルートで、頭がすっと整う心地よいひとときを楽しめます。",
            f"約{distance_km:.1f}kmの落ち着いた道のりを歩きながら、思考が冴える爽やかな時間を味わえます。",
            f"約{distance_km:.1f}kmの静かな散歩道で、ゆっくりと自分のペースに戻れる時間が広がります。",
        ],
        "exercise": [
            f"アップダウンも楽しめる約{distance_km:.1f}kmのルートで、気分が高まる爽快ウォークに出かけましょう。",
            f"約{distance_km:.1f}kmのアクティブな道のりで、体が目覚めるワクワク散歩が始まります。",
            f"心拍が上がる約{distance_km:.1f}kmのルートで、汗と一緒に気分もリフレッシュしましょう。",
        ],
        "refresh": [
            f"街の活気を感じながら歩ける約{distance_km:.1f}kmのルートで、気分が弾むリフレッシュを味わえます。",
            f"約{distance_km:.1f}kmの街歩きで、景色の変化を楽しむ軽やかな気分転換に出かけられます。",
            f"にぎわいを感じる約{distance_km:.1f}kmの道のりで、心がほどける散歩時間を楽しめます。",
        ],
        "nature": [
            f"緑に包まれながら歩ける約{distance_km:.1f}kmのルートで、心がほどける自然時間を満喫できます。",
            f"約{distance_km:.1f}kmの自然を感じる散歩道で、深呼吸したくなる景色が続きます。",
            f"木漏れ日を感じる約{distance_km:.1f}kmのルートで、癒やしの散策が待っています。",
        ],
    }
    options = theme_summaries.get(
        theme,
        [f"約{distance_km:.1f}kmを{duration_min:.0f}分で歩ける、歩き出したくなる散歩コースです。"],
    )
    return random.choice(options)


def _fallback_title(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    theme_titles = {
        "think": ["静けさの川沿い", "ひと息つける小道", "思索の並木道"],
        "exercise": ["アップダウン燃焼", "坂道チャージ", "アクティブ散歩"],
        "refresh": ["街なかリフレッシュ", "きらめき街歩き", "気分転換の小径"],
        "nature": ["木漏れ日の森歩き", "緑風のさんぽ道", "自然に浸る散策"],
    }
    base = random.choice(theme_titles.get(theme, ["散歩"]))
    return f"{base}コース"


def fallback_title(theme: str, distance_km: float, duration_min: float, spots: Optional[list]) -> str:
    return _fallback_title(theme, distance_km, duration_min, spots)


def _theme_to_natural(theme: str) -> str:
    theme_map = {
        "exercise": "運動やエクササイズ",
        "think": "思考やリフレッシュ",
        "refresh": "気分転換やリフレッシュ",
        "nature": "自然や緑",
    }
    return theme_map.get(theme, theme)


async def _invoke_structured(prompt: str, *, temperature: float, max_output_tokens: int, schema: type) -> object:
    llm = _get_llm(temperature=temperature, max_output_tokens=max_output_tokens)
    if llm is None:
        raise RuntimeError("Vertex LLM is not configured")
    runnable = llm.with_structured_output(schema)
    return await runnable.ainvoke(prompt)


async def _invoke_raw(prompt: str, *, temperature: float, max_output_tokens: int) -> object:
    llm = _get_llm(temperature=temperature, max_output_tokens=max_output_tokens)
    if llm is None:
        raise RuntimeError("Vertex LLM is not configured")
    return await llm.ainvoke(prompt)


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
            result = await _invoke_structured(
                prompt,
                temperature=attempt["temperature"],
                max_output_tokens=attempt["max_out"],
                schema=DescriptionResponse,
            )
            parsed = _coerce_structured(result, DescriptionResponse)
            text = parsed.description
            banned = _contains_forbidden(text, forbidden_words)
            if banned:
                raise ValueError(f"forbidden word found: {banned}")
            return text
        except (OutputParserException, ValidationError, ValueError) as e:
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
            result = await _invoke_structured(
                prompt,
                temperature=attempt["temperature"],
                max_output_tokens=attempt["max_out"],
                schema=TitleResponse,
            )
            parsed = _coerce_structured(result, TitleResponse)
            text = parsed.title
            banned = _contains_forbidden(text, forbidden_words)
            if banned:
                raise ValueError(f"forbidden word found: {banned}")
            return text
        except (OutputParserException, ValidationError, ValueError) as e:
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
            "max_out": max(max_out, 320),
        },
        {
            "strict": True,
            "title_min": 8,
            "title_max": 18,
            "desc_min": 90,
            "desc_max": 120,
            "temperature": min(temperature, 0.2),
            "max_out": max(max_out, 320),
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
            result = await _invoke_raw(
                prompt,
                temperature=attempt["temperature"],
                max_output_tokens=attempt["max_out"],
            )
            if hasattr(result, "content"):
                result = result.content
            parsed = _coerce_structured(result, TitleDescriptionResponse)
            title = parsed.title
            description = parsed.description
            banned = _contains_forbidden(title, forbidden_words) or _contains_forbidden(description, forbidden_words)
            if banned:
                raise ValueError(f"forbidden word found: {banned}")
            return {"title": title, "description": description}
        except (OutputParserException, ValidationError, ValueError) as e:
            logger.warning("[Vertex LLM Title+Summary Invalid] err=%r", e)
        except Exception as e:
            logger.exception("[Vertex LLM Title+Summary Error] err=%r", e)

    return {
        "title": _fallback_title(theme, distance_km, duration_min, spots),
        "description": _fallback_summary(theme, distance_km, duration_min, spots),
    }
