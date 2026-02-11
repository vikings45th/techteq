from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb
from fastapi import FastAPI, HTTPException
from google.cloud import storage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Vertex Predictor", version="1.0.0")


class PredictRequest(BaseModel):
    instances: List[Dict[str, Any]] = Field(default_factory=list)


class PredictResponse(BaseModel):
    predictions: List[float]
    model_version: Optional[str] = None


class ModelBundle:
    def __init__(self) -> None:
        self.model: Optional[xgb.XGBRegressor] = None
        self.feature_columns: List[str] = []
        self.model_version: Optional[str] = None

    def load(self) -> None:
        model_path = _resolve_path(
            os.getenv("MODEL_GCS_URI", ""),
            os.getenv("MODEL_PATH", ""),
            "model.xgb.json",
        )
        features_path = _resolve_path(
            os.getenv("FEATURES_GCS_URI", ""),
            os.getenv("FEATURES_PATH", ""),
            "feature_columns.json",
        )
        metadata_path = _resolve_path(
            os.getenv("METADATA_GCS_URI", ""),
            os.getenv("METADATA_PATH", ""),
            "metadata.json",
            required=False,
        )

        if not model_path or not features_path:
            raise RuntimeError("MODEL_GCS_URI/MODEL_PATH and FEATURES_GCS_URI/FEATURES_PATH are required.")

        with Path(features_path).open("r", encoding="utf-8") as f:
            self.feature_columns = json.load(f)

        if metadata_path and Path(metadata_path).exists():
            with Path(metadata_path).open("r", encoding="utf-8") as f:
                metadata = json.load(f)
                self.model_version = metadata.get("model_version")

        model = xgb.XGBRegressor()
        model.load_model(str(model_path))
        self.model = model


MODEL = ModelBundle()


@app.on_event("startup")
def _startup() -> None:
    MODEL.load()
    logger.info("Model loaded. features=%d", len(MODEL.feature_columns))


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    if MODEL.model is None or not MODEL.feature_columns:
        raise HTTPException(status_code=500, detail="Model not loaded.")
    if not req.instances:
        return PredictResponse(predictions=[], model_version=MODEL.model_version)

    matrix = _vectorize_instances(req.instances, MODEL.feature_columns)
    preds = MODEL.model.predict(matrix)
    predictions = [float(x) for x in preds]
    return PredictResponse(predictions=predictions, model_version=MODEL.model_version)


def _vectorize_instances(
    instances: List[Dict[str, Any]],
    feature_columns: List[str],
) -> np.ndarray:
    rows: List[List[float]] = []
    for inst in instances:
        values: List[float] = []
        for name in feature_columns:
            raw = inst.get(name, None)
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
        rows.append(values)
    return np.asarray(rows, dtype=float)


def _resolve_path(
    gcs_uri: str,
    local_path: str,
    default_name: str,
    required: bool = True,
) -> Optional[str]:
    if gcs_uri:
        return _download_gcs(gcs_uri, default_name)
    if local_path:
        return local_path
    if required:
        return None
    return None


def _download_gcs(gcs_uri: str, filename: str) -> str:
    bucket_name, blob_path = _parse_gcs_uri(gcs_uri)
    local_path = str(Path("/tmp") / filename)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)
    return local_path


def _parse_gcs_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {uri}")
    path = uri[5:]
    if "/" not in path:
        raise ValueError(f"Invalid GCS URI: {uri}")
    bucket, blob = path.split("/", 1)
    return bucket, blob
