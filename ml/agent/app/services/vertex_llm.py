from __future__ import annotations

from typing import Any, Dict, Optional
import google.auth
import google.auth.transport.requests
import httpx

from app.settings import settings


def _get_auth_token() -> str:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


async def generate_summary(
    *,
    theme: str,
    distance_km: float,
    duration_min: float,
    spots: Optional[list] = None,
    text: Optional[str] = None,
) -> Optional[str]:
    project = settings.VERTEX_PROJECT
    location = settings.VERTEX_LOCATION
    model = settings.VERTEX_TEXT_MODEL
    if not project or not location or not model:
        return None

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

    token = _get_auth_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    endpoint = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"
    )

    body: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": settings.VERTEX_TEMPERATURE,
            "topP": settings.VERTEX_TOP_P,
            "topK": settings.VERTEX_TOP_K,
            "maxOutputTokens": 128,
        },
    }

    print(f"[Vertex Gemini Call] model={model} project={project} location={location}")

    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SEC) as client:
        resp = await client.post(endpoint, headers=headers, json=body)

    if resp.status_code != 200:
        print(f"[Vertex Gemini HTTP] status={resp.status_code} body={resp.text}")
        return None

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        print("[Vertex Gemini Empty] candidates is empty")
        return None

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if not parts:
        print("[Vertex Gemini Empty] parts is empty")
        return None

    text = parts[0].get("text")
    if isinstance(text, str) and text.strip():
        out = text.strip()
        print(f"[Vertex Gemini Result] len={len(out)}")
        return out

    print(f"[Vertex Gemini Empty] unexpected candidate format: {candidates[0]}")
    return None
