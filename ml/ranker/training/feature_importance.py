"""
既存の XGBoost モデルから特徴量重要度を取得し、表示するスクリプト。

使い方:
  python feature_importance.py [--model PATH] [--features PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import xgboost as xgb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract feature importance from trained XGBoost model")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Path to model.xgb.json (default: ../artifacts/model.xgb.json)",
    )
    parser.add_argument(
        "--features",
        type=str,
        default=None,
        help="Path to feature_columns.json (default: same dir as model)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional: write importance JSON to this path",
    )
    return parser.parse_args()


def load_feature_columns(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("feature_columns", data)


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    model_path = Path(args.model) if args.model else script_dir.parent / "artifacts" / "model.xgb.json"
    features_path = Path(args.features) if args.features else model_path.parent / "feature_columns.json"

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not features_path.exists():
        raise FileNotFoundError(f"Feature columns not found: {features_path}")

    feature_columns = load_feature_columns(features_path)
    booster = xgb.Booster()
    booster.load_model(str(model_path))

    # importance_type: gain (改善に寄与した度合い), weight (分割で使われた回数), cover
    importance_types = ["gain", "weight", "cover"]
    results = {}

    for imp_type in importance_types:
        raw = booster.get_score(importance_type=imp_type)
        # f0, f1, ... -> feature name
        by_name = {}
        for key, value in raw.items():
            if key.startswith("f"):
                idx = int(key[1:])
                if 0 <= idx < len(feature_columns):
                    by_name[feature_columns[idx]] = float(value)
        results[imp_type] = by_name

    # 表示用: gain でソート（全特徴量、0 のものも含む）
    gain = results["gain"]
    total_gain = sum(gain.values()) or 1.0
    rows = []
    for name in feature_columns:
        g = gain.get(name, 0.0)
        pct = 100.0 * g / total_gain if total_gain else 0.0
        w = results["weight"].get(name, 0)
        c = results["cover"].get(name, 0)
        rows.append({"feature": name, "gain": round(g, 4), "gain_pct": round(pct, 2), "weight": int(w), "cover": round(c, 2)})
    rows.sort(key=lambda x: -x["gain"])

    print("Feature importance (by gain)")
    print("-" * 72)
    print(f"{'feature':<28} {'gain':>10} {'gain_%':>8} {'weight':>8} {'cover':>10}")
    print("-" * 72)
    for r in rows:
        print(f"{r['feature']:<28} {r['gain']:>10.4f} {r['gain_pct']:>7.2f}% {r['weight']:>8} {r['cover']:>10.2f}")
    print("-" * 72)
    print(f"{'TOTAL (non-zero)':<28} {total_gain:>10.4f} {'100.00':>7}%")

    # elevation / steps 関連の注目特徴量
    focus = ["elevation_gain_m", "elevation_density", "has_stairs"]
    print("\n--- ボトルネック候補 (elevation / steps 関連) ---")
    for name in focus:
        g = gain.get(name, 0.0)
        pct = 100.0 * g / total_gain
        rank = next((i + 1 for i, r in enumerate(rows) if r["feature"] == name), None)
        print(f"  {name}: gain={g:.4f} ({pct:.2f}%), rank={rank}/{len(rows)}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump({"by_gain": rows, "raw": {k: {kk: vv for kk, vv in v.items()} for k, v in results.items()}}, f, ensure_ascii=False, indent=2)
        print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
