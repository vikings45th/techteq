from __future__ import annotations

from typing import Any, Dict, Optional

import google.auth
import google.auth.transport.requests
import httpx

from app.settings import settings


def _get_auth_token(audience: str) -> str:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


async def generate_summary(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
) -> Optional[str]:
    """
    Generate a short natural sentence using Vertex text model.
    Returns None if project/model not configured.
    """
    project = settings.VERTEX_PROJECT
    location = settings.VERTEX_LOCATION
    model = settings.VERTEX_TEXT_MODEL
    if not project:
        return None

    endpoint = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:predict"

    spots_text = ""
    if spots:
        spot_names = ", ".join([s.get("name", "") for s in spots if s.get("name")])
        if spot_names:
            spots_text = f" 見どころ: {spot_names}。"

    prompt = (
        f"以下の散歩ルートの紹介文を日本語で一文で作成してください。"
        f" テーマ: {theme}。目安距離: {distance_km:.1f}km。所要時間: {duration_min:.0f}分。"
        f"{spots_text} 丁寧で簡潔に。"
    )

    token = _get_auth_token(endpoint)
    headers = {"Authorization": f"Bearer {token}"}
    body: Dict[str, Any] = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "temperature": settings.VERTEX_TEMPERATURE,
            "topP": settings.VERTEX_TOP_P,
            "topK": settings.VERTEX_TOP_K,
            "maxOutputTokens": 128,
        },
    }
    
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SEC) as client:
        print(f"[Vertex LLM Call] model={settings.VERTEX_TEXT_MODEL} project={settings.VERTEX_PROJECT} location={settings.VERTEX_LOCATION}")
        
        resp = await client.post(endpoint, headers=headers, json=body)
        
        print(f"[Vertex LLM Result] len={len(text) if text else 0}")
        if resp.status_code != 200:
            return None
        data = resp.json()
        predictions = data.get("predictions") or []
        if not predictions:
            return None
        text = predictions[0].get("content") or predictions[0].get("output")
        if isinstance(text, str):
            return text.strip()
        return None
    
