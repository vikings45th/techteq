from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import xgboost as xgb

from app.settings import settings


class ModelScorer:
    """シャドウ用のモデルスコアリング（XGBoost推論）"""

    def __init__(self, timeout_s: float | None = None, mode: str | None = None) -> None:
        self._timeout_s = timeout_s if timeout_s is not None else settings.MODEL_TIMEOUT_S
        self._mode = (mode or settings.MODEL_SHADOW_MODE or "xgb").lower()
        self._model: Optional[xgb.XGBRegressor] = None
        self._feature_columns: list[str] = []
        self._load_error: Optional[str] = None

        if self._mode == "xgb":
            try:
                self._load_model()
            except Exception as exc:
                self._load_error = str(exc)

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
            if self._mode != "xgb":
                return None, self._elapsed_ms(start), "model_mode_unsupported"
            if self._load_error or self._model is None or not self._feature_columns:
                return None, self._elapsed_ms(start), "model_not_loaded"

            vector = self._vectorize_features(features)
            pred = float(self._model.predict(vector)[0])
            return pred, self._elapsed_ms(start), "ok"
        except Exception:
            return None, self._elapsed_ms(start), "model_error"

    def _load_model(self) -> None:
        model_path = Path(settings.MODEL_PATH)
        features_path = Path(settings.MODEL_FEATURES_PATH)

        if not model_path.exists():
            raise FileNotFoundError(f"MODEL_PATH not found: {model_path}")
        if not features_path.exists():
            raise FileNotFoundError(f"MODEL_FEATURES_PATH not found: {features_path}")

        with features_path.open("r", encoding="utf-8") as f:
            self._feature_columns = json.load(f)

        model = xgb.XGBRegressor()
        model.load_model(str(model_path))
        self._model = model

    def _vectorize_features(self, features: Dict[str, Any]) -> np.ndarray:
        values: list[float] = []
        for name in self._feature_columns:
            raw = features.get(name, None)
            if isinstance(raw, bool):
                values.append(1.0 if raw else 0.0)
                continue
            if raw is None:
                values.append(np.nan)
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                values.append(np.nan)
        return np.array([values], dtype=float)

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
