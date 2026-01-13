from typing import Any, Dict, List, Tuple
import httpx

from app.settings import settings


async def rank_routes(
    request_id: str,
    routes: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Call internal Ranker API. Partial success allowed.
    routes: [{"route_id": "...", "features": {...}}, ...]
    Returns (scores, failed_route_ids)
    """
    payload = {"request_id": request_id, "routes": routes}

    timeout = httpx.Timeout(settings.RANKER_TIMEOUT_SEC)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{settings.RANKER_URL}/rank", json=payload)

    if r.status_code == 200:
        data = r.json()
        return data.get("scores", []), data.get("failed_route_ids", [])
    if r.status_code != 200:
        print(f"[Ranker HTTP] status={r.status_code} body={r.text}")
    if r.status_code == 422:
        # Ranker could not score any route
        return [], [x.get("route_id") for x in routes if "route_id" in x]
    r.raise_for_status()
    return [], []
