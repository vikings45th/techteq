from __future__ import annotations
from typing import Optional
import vertexai
from vertexai.generative_models import GenerativeModel

from app.settings import settings


async def generate_summary(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> Optional[str]:
    project = settings.VERTEX_PROJECT
    location = settings.VERTEX_LOCATION
    model_name = settings.VERTEX_TEXT_MODEL

    if not project or not location or not model_name:
        return None

    vertexai.init(project=project, location=location)

    spots_text = ""
    if spots:
        names = ", ".join(s.get("name") for s in spots if s.get("name"))
        if names:
            spots_text = f" 見どころ: {names}。"

    prompt = (
        "以下の散歩ルートの紹介文を日本語で一文で作成してください。"
        f" テーマ: {theme}。目安距離: {distance_km:.1f}km。"
        f" 所要時間: {duration_min:.0f}分。"
        f"{spots_text} 丁寧で簡潔に。"
    )

    print(f"[Vertex Gemini SDK Call] model={model_name}")

    model = GenerativeModel(model_name)
    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": settings.VERTEX_TEMPERATURE,
            "max_output_tokens": 64,
        },
    )

    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        print(f"[Vertex Gemini SDK Result] len={len(text)}")
        return text.strip()

    print("[Vertex Gemini SDK Empty]")
    return None
