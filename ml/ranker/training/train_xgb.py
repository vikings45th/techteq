from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from google.cloud import bigquery

DEFAULT_FEATURE_COLUMNS: List[str] = [
    "distance_km",
    "duration_min",
    "loop_closure_m",
    "bbox_area",
    "path_length_ratio",
    "turn_count",
    "turn_density",
    "theme_exercise",
    "theme_think",
    "theme_refresh",
    "theme_nature",
    "round_trip_req",
    "round_trip_fit",
    "distance_error_ratio",
    "relaxation_step",
    "candidate_rank_in_theme",
    "has_stairs",
    "elevation_gain_m",
    "elevation_density",
    "poi_density",
    "park_poi_ratio",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train XGBoost regressor for ranker shadow model")
    parser.add_argument("--project", type=str, default=None, help="GCP project id")
    parser.add_argument("--dataset", type=str, default=None, help="BigQuery dataset")
    parser.add_argument("--table", type=str, default=None, help="BigQuery table name")
    parser.add_argument("--query", type=str, default=None, help="Custom SQL query")
    parser.add_argument("--output-dir", type=str, default="artifacts", help="Artifacts output dir")
    parser.add_argument(
        "--feature-columns",
        type=str,
        default=None,
        help="Feature columns JSON file path (optional)",
    )
    parser.add_argument("--model-version", type=str, default="unknown", help="Model version tag")
    return parser.parse_args()


def load_feature_columns(path: Optional[str]) -> List[str]:
    if not path:
        return DEFAULT_FEATURE_COLUMNS
    feature_path = Path(path)
    with feature_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_query(table_id: str, feature_columns: Iterable[str]) -> str:
    features_sql = ", ".join(feature_columns)
    return f"""
    SELECT
        {features_sql},
        feedback_rating,
        split
    FROM `{table_id}`
    WHERE feedback_rating IS NOT NULL
    """


def fetch_training_data(
    client: bigquery.Client, query: str
) -> pd.DataFrame:
    job = client.query(query)
    df = job.to_dataframe()
    if df.empty:
        raise ValueError("No training data returned from BigQuery.")
    return df


def prepare_splits(
    df: pd.DataFrame, feature_columns: List[str]
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if "split" not in df.columns:
        return df.copy(), pd.DataFrame(), pd.DataFrame()

    split_norm = df["split"].astype(str).str.lower()
    split_norm = split_norm.replace(
        {
            "validate": "valid",
            "validation": "valid",
            "val": "valid",
        }
    )
    df = df.copy()
    df["_split_norm"] = split_norm

    train_df = df[df["_split_norm"] == "train"].copy()
    valid_df = df[df["_split_norm"] == "valid"].copy()
    test_df = df[df["_split_norm"] == "test"].copy()
    if train_df.empty:
        train_df = df.copy()
    return train_df, valid_df, test_df


def to_matrix(df: pd.DataFrame, feature_columns: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    X = df[feature_columns].copy()
    for col in X.columns:
        if X[col].dtype == bool:
            X[col] = X[col].astype(int)
    X = X.apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(df["feedback_rating"], errors="coerce")
    X = X.to_numpy(dtype=float)
    y = y.to_numpy(dtype=float)
    return X, y


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_valid: Optional[np.ndarray] = None,
    y_valid: Optional[np.ndarray] = None,
) -> xgb.XGBRegressor:
    model = xgb.XGBRegressor(
        objective="reg:pseudohubererror",
        eval_metric="mae",
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        n_jobs=4,
    )
    eval_set = []
    if X_valid is not None and y_valid is not None and len(y_valid) > 0:
        eval_set = [(X_valid, y_valid)]
    try:
        model.fit(X_train, y_train, eval_set=eval_set, verbose=False)
    except ValueError:
        model = xgb.XGBRegressor(
            objective="reg:squarederror",
            eval_metric="mae",
            n_estimators=300,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            n_jobs=4,
        )
        model.fit(X_train, y_train, eval_set=eval_set, verbose=False)
    return model


def mae_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[float, float]:
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    return mae, rmse


def main() -> None:
    args = parse_args()
    feature_columns = load_feature_columns(args.feature_columns)

    if args.query:
        query = args.query
    else:
        if not args.dataset or not args.table:
            raise ValueError("dataset/table or query must be provided.")
        project = args.project or bigquery.Client().project
        table_id = f"{project}.{args.dataset}.{args.table}"
        query = build_query(table_id, feature_columns)

    client = bigquery.Client(project=args.project)
    df = fetch_training_data(client, query)
    train_df, valid_df, test_df = prepare_splits(df, feature_columns)

    X_train, y_train = to_matrix(train_df, feature_columns)
    X_valid, y_valid = (None, None)
    if not valid_df.empty:
        X_valid, y_valid = to_matrix(valid_df, feature_columns)

    model = train_model(X_train, y_train, X_valid, y_valid)

    metrics = {}
    if X_valid is not None and y_valid is not None and len(y_valid) > 0:
        pred_valid = model.predict(X_valid)
        mae, rmse = mae_rmse(y_valid, pred_valid)
        metrics["valid_mae"] = mae
        metrics["valid_rmse"] = rmse
        print(f"valid MAE={mae:.4f} RMSE={rmse:.4f}")

    if not test_df.empty:
        X_test, y_test = to_matrix(test_df, feature_columns)
        pred_test = model.predict(X_test)
        mae, rmse = mae_rmse(y_test, pred_test)
        metrics["test_mae"] = mae
        metrics["test_rmse"] = rmse
        print(f"test MAE={mae:.4f} RMSE={rmse:.4f}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.xgb.json"
    features_path = output_dir / "feature_columns.json"
    metadata_path = output_dir / "metadata.json"

    model.save_model(str(model_path))
    with features_path.open("w", encoding="utf-8") as f:
        json.dump(feature_columns, f, ensure_ascii=False, indent=2)

    metadata = {
        "model_version": args.model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_columns": feature_columns,
        "metrics": metrics,
    }
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"saved model: {model_path}")
    print(f"saved feature columns: {features_path}")
    print(f"saved metadata: {metadata_path}")


if __name__ == "__main__":
    main()
