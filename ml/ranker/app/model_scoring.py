from __future__ import annotations

import time
from typing import Any, Dict, Tuple, Optional

from app.settings import settings


class ModelScorer:
    """シャドウ用のモデルスコアリング（後で差し替えやすい形で分離）"""

    def __init__(self, timeout_s: float | None = None, mode: str | None = None) -> None:
        self._timeout_s = timeout_s if timeout_s is not None else settings.MODEL_TIMEOUT_S
        self._mode = (mode or settings.MODEL_SHADOW_MODE or "stub").lower()

    def score(self, features: Dict[str, Any]) -> Tuple[Optional[float], int, str]:
        """
        ルート特徴量からモデルスコアを返す。

        Returns:
            (score, latency_ms, status)
        """
        start = time.perf_counter()
        try:
            if self._mode == "disabled":
                return None, self._elapsed_ms(start), "model_disabled"
            if self._mode == "stub":
                score = self._stub_score(features)
                return score, self._elapsed_ms(start), "ok"
            # 将来の推論に置き換えるエントリポイント
            raise NotImplementedError(f"MODEL_SHADOW_MODE={self._mode} is not implemented")
        except Exception:
            return None, self._elapsed_ms(start), "model_error"

    def _stub_score(self, features: Dict[str, Any]) -> float:
        """
        ルールとは独立した簡易スコア（0.0-1.0）。
        特徴量の一部を軽く正規化して合算する。
        """
        distance_error_ratio = float(features.get("distance_error_ratio", 0.0))
        loop_closure_m = float(features.get("loop_closure_m", 1000.0))
        poi_density = float(features.get("poi_density", 0.0))
        park_poi_ratio = float(features.get("park_poi_ratio", 0.0))
        spot_type_diversity = float(features.get("spot_type_diversity", 0.0))

        distance_component = max(0.0, 1.0 - min(distance_error_ratio, 1.0))
        loop_component = max(0.0, 1.0 - min(loop_closure_m / 1000.0, 1.0))
        poi_component = min(poi_density, 1.0) * 0.6 + min(park_poi_ratio, 1.0) * 0.4
        diversity_component = min(max(spot_type_diversity, 0.0), 1.0)

        score = (
            distance_component * 0.4
            + loop_component * 0.2
            + poi_component * 0.2
            + diversity_component * 0.2
        )
        return max(0.0, min(1.0, score))

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)
