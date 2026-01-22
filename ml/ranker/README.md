# Ranker API

ルート候補をスコアリングしてランキングするAPIサービスです。

## 📋 目次

- [概要](#概要)
- [API仕様](#api仕様)
- [スコアリングロジック](#スコアリングロジック)
- [実装詳細](#実装詳細)
- [テスト](#テスト)
- [デプロイ](#デプロイ)

## 概要

Ranker APIは、Agent APIから送信されたルート候補を評価し、スコアリングするサービスです。意思決定はルールベースのスコアを維持しつつ、XGBoost回帰モデルによる「シャドウ推論」を実行し、BigQueryに保存します。

### 主な機能

- **ルートスコアリング**: 特徴量に基づくルート品質評価
- **複数ルートの並列評価**: 最大5件のルートを一度に評価
- **部分的な成功を許容**: 一部のルートが失敗してもOK
- **スコア内訳の提供**: デバッグ用のスコア内訳情報（`model_score`を含む）
- **シャドウ推論ログ**: モデルスコア/レイテンシをBigQueryへ保存

## API仕様

### エンドポイント

#### `POST /rank`

ルート候補をスコアリング

**リクエスト (`RankRequest`):**

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "routes": [
    {
      "route_id": "route_001",
      "features": {
        "distance_km": 3.2,
        "duration_min": 45,
        "distance_error_ratio": 0.067,
        "round_trip_req": 1,
        "round_trip_fit": 1,
        "loop_closure_m": 50.0,
        "park_poi_ratio": 0.3,
        "poi_density": 0.5,
        "spot_type_diversity": 0.6,
        "detour_over_ratio": 0.1,
        "theme_exercise": 1,
        "has_stairs": 1,
        "elevation_density": 25.0
      }
    }
  ]
}
```

**制約:**
- `routes`: 1件以上5件以下
- `features`: 任意キーを許容（未使用のキーは無視）

**レスポンス (`RankResponse`):**

```json
{
  "scores": [
    {
      "route_id": "route_001",
      "score": 0.85,
      "breakdown": {
        "base": 0.5,
        "distance_penalty": -0.033,
        "loop_closure_bonus": 0.2,
        "poi_bonus": 0.145,
        "diversity_bonus": 0.072,
        "detour_penalty": -0.015,
        "exercise_bonus": 0.35,
        "final_score": 0.85,
        "rule_score": 0.85,
        "model_score": 0.61,
        "model_latency_ms": 3
      }
    }
  ],
  "failed_route_ids": []
}
```

**説明:**
- `scores`: スコアリング成功したルートのリスト（スコアは0.0-1.0の範囲、高い順にソート済み）
- `failed_route_ids`: スコアリング失敗したルートIDのリスト
- `breakdown`: スコア内訳（デバッグ用、各要素の寄与度）
  - `rule_score`: ルールスコア
  - `model_score`: シャドウモデルスコア（失敗時はnull）

**エラー:**
- `422 Unprocessable Entity`: すべてのルートのスコアリングに失敗した場合

#### `GET /health`

ヘルスチェック

**レスポンス例:**
```json
{
  "status": "ok"
}
```

## スコアリングロジック

現在はルールベーススコアを本番の意思決定に利用します。モデル推論は「シャドウ」として実行し、レスポンス内の`breakdown.model_score`とBigQueryログに保存します。

### 基本スコア

ベーススコア: `0.5`

### スコア計算要素

#### 1. 距離乖離ペナルティ

目標距離との誤差が小さいほど良い。

```python
distance_penalty = -distance_error_ratio * 0.5
```

- `distance_error_ratio`: 目標距離との誤差比率（小さいほど良い）

#### 2. ループ閉鎖ボーナス

往復ルート要求時、ループ閉鎖距離が小さいほど良い。

```python
if round_trip_req:
    if loop_closure_m <= 100.0:
        loop_closure_bonus = 0.2  # 100m以内ならボーナス
    elif loop_closure_m <= 500.0:
        loop_closure_bonus = 0.1  # 500m以内なら小さいボーナス
    if round_trip_fit:
        loop_closure_bonus = max(loop_closure_bonus, 0.2)
```

- `loop_closure_m`: ループ閉鎖距離（m、小さいほど良い）
- `round_trip_fit`: 往復ルート適合度（1 or 0）

#### 3. POIボーナス

公園POI比率とPOI密度が高いほど良い。

```python
poi_bonus = park_poi_ratio * 0.15 + min(poi_density, 1.0) * 0.1
```

- `park_poi_ratio`: 公園POI比率（大きいほど良い）
- `poi_density`: POI密度（大きいほど良い、1.0でクランプ）

#### 4. 運動テーマボーナス

Exerciseテーマの場合、階段と標高差密度を考慮。

```python
if theme_exercise:
    if has_stairs:
        exercise_bonus += 0.15  # 階段があると運動強度が高い
    
    # 標高差密度（m/km）に基づくボーナス
    if 10.0 <= elevation_density <= 50.0:
        exercise_bonus += 0.2  # 適度な坂道は良い
    elif 5.0 <= elevation_density < 10.0:
        exercise_bonus += 0.1  # 軽い坂道も良い
    elif elevation_density > 50.0:
        exercise_bonus += 0.1  # 急な坂道も運動強度は高い
```

- `has_stairs`: 階段の有無（1 or 0）
- `elevation_density`: 標高差密度（m/km）
  - 10-50m/km: 適度な坂道（+0.2）
  - 5-10m/km: 軽い坂道（+0.1）
  - 50m/km以上: 急な坂道（+0.1）

#### 5. スポット多様性ボーナス

スポットのカテゴリが分散しているほど良い。

```python
diversity_bonus = min(max(spot_type_diversity, 0.0), 1.0) * 0.12
```

- `spot_type_diversity`: スポットタイプ多様性（0.0-1.0）

#### 6. 寄り道超過ペナルティ

許容寄り道距離を超えた分を減点。

```python
detour_penalty = -min(max(detour_over_ratio, 0.0), 1.0) * 0.15
```

- `detour_over_ratio`: 逸脱超過比率（0.0-∞、大きいほど悪い）

### 最終スコア

```python
score = base + distance_penalty + loop_closure_bonus + poi_bonus + diversity_bonus + detour_penalty + exercise_bonus
score = max(0.0, min(1.0, score))  # 0.0-1.0の範囲にクリップ
```

**使用している特徴量:**
- `distance_error_ratio`: 目標距離との誤差比率（小さいほど良い）
- `round_trip_req`: 往復ルート要求フラグ（1 or 0）
- `round_trip_fit`: 往復ルート適合度（1 or 0）
- `loop_closure_m`: ループ閉鎖距離（m、小さいほど良い）
- `park_poi_ratio`: 公園POI比率（大きいほど良い）
- `poi_density`: POI密度（大きいほど良い）
- `spot_type_diversity`: スポットタイプ多様性（大きいほど良い）
- `detour_over_ratio`: 寄り道超過比率（小さいほど良い）
- `theme_exercise`: 運動テーマフラグ（1 or 0）
- `has_stairs`: 階段の有無（1 or 0）
- `elevation_density`: 標高差密度（m/km）

**注意:** 将来的にVertex AIを使った機械学習モデルに置き換える予定です。

## 実装詳細

### 技術スタック

- **FastAPI**: REST APIフレームワーク
- **Pydantic**: スキーマ検証
- **Python 3.11+**: 実行環境

### 特徴

- **部分的な成功を許容**: 一部のルートが失敗してもOK（`failed_route_ids`に記録）
- **スコア内訳の提供**: デバッグ用のスコア内訳情報（`breakdown`）
- **スコア順ソート**: レスポンスはスコアが高い順にソート済み

### コード構造

```
ml/ranker/
├── app/
│   ├── main.py              # FastAPIアプリケーション、スコアリングロジック
│   ├── model_scoring.py     # シャドウ推論インターフェース
│   ├── bq_logger.py         # BigQueryログ書き込み
│   ├── schemas.py           # データスキーマ（Pydantic）
│   └── settings.py          # 設定管理
├── bq/
│   └── rank_result_shadow.sql # rank_resultテーブルDDL
├── artifacts/              # 学習成果物の出力先（生成物）
├── models/                 # 推論時に参照する成果物
├── training/
│   ├── train_xgb.py         # XGBoost学習スクリプト
│   └── requirements.txt     # 学習用依存
├── Dockerfile
├── requirements.txt
├── README.md
└── test_ranker.py           # テストスクリプト
```

## テスト

### テストスクリプト

```bash
cd ml/ranker
python test_ranker.py
```

テストスクリプトは、様々な特徴量の組み合わせでスコアリングをテストします。

### ローカル開発

```bash
# 依存関係のインストール
pip install -r requirements.txt

# サーバー起動
uvicorn app.main:app --reload --port 8080
```

### 手動テスト

```bash
# 環境変数（例）
export MODEL_SHADOW_MODE=xgb
export MODEL_VERSION=shadow_xgb_v1
export RANKER_VERSION=rule_v1
export BQ_DATASET=firstdown_mvp
export BQ_RANK_RESULT_TABLE=rank_result
export MODEL_PATH=models/model.xgb.json
export MODEL_FEATURES_PATH=models/feature_columns.json

# ヘルスチェック
curl http://localhost:8080/health

# スコアリングリクエスト
curl -X POST http://localhost:8080/rank \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-001",
    "routes": [
      {
        "route_id": "route_001",
        "features": {
          "distance_error_ratio": 0.1,
          "round_trip_req": 1,
          "round_trip_fit": 1,
          "loop_closure_m": 50.0,
          "park_poi_ratio": 0.3,
          "poi_density": 0.5
        }
      }
    ]
  }'
```

### BigQuery テーブル

`rank_result` テーブルのDDLは `ml/ranker/bq/rank_result_shadow.sql` にあります。  
モデル推論・BQ書き込みの失敗はレスポンスに影響せず、ログにのみ記録されます。

## 学習とモデル配置

### 学習（BigQueryから取得）

```bash
cd ml/ranker
pip install -r training/requirements.txt

# 例: BigQueryの学習用ビューから学習
python training/train_xgb.py \
  --project firstdown-482704 \
  --dataset firstdown_mvp \
  --table training_view_poc_aug_v2 \
  --model-version shadow_xgb_v1 \
  --output-dir artifacts
```

学習後、以下の成果物が生成されます。

- `artifacts/model.xgb.json`
- `artifacts/feature_columns.json`
- `artifacts/metadata.json`

### 推論用成果物の配置

```bash
# 成果物を推論用ディレクトリへ配置
cp artifacts/model.xgb.json models/model.xgb.json
cp artifacts/feature_columns.json models/feature_columns.json
```

Cloud Run では `models/` をイメージに同梱するか、ボリュームでマウントしてください。

### 実行確認（ローカル）

```bash
export MODEL_SHADOW_MODE=xgb
export MODEL_VERSION=shadow_xgb_v1
export MODEL_PATH=models/model.xgb.json
export MODEL_FEATURES_PATH=models/feature_columns.json

uvicorn app.main:app --reload --port 8080
```

### 推論の注意点

- 学習データは `split` 列（train/valid/test）を前提としています
- `request_id` 単位での分割が未整備の場合、データリークの恐れがあるため注意してください

## タイムアウト

Agentからの呼び出しにはタイムアウトが設定されています（デフォルト: 10秒）。

タイムアウトが発生した場合、Agent APIはフォールバック処理を行い、最初のルート候補を選択します。

## デプロイ

Cloud Runにデプロイされます。設定は`.github/workflows/deploy-ranker.yml`を参照してください。

### デプロイワークフロー

1. GitHub Actionsが`ml/ranker/**`への変更を検知
2. Dockerイメージをビルド
3. Artifact Registryにプッシュ
4. Cloud Runにデプロイ

### 必要なGCPリソース

1. **Cloud Run**: サービス実行環境
2. **Artifact Registry**: Dockerイメージ保存

## トラブルシューティング

### よくある問題

#### 1. すべてのルートのスコアリングに失敗

**症状**: `422 Unprocessable Entity` エラー

**原因**:
- 特徴量の形式が不正
- 必須フィールドが欠落

**解決方法**:
- リクエストの特徴量を確認
- ログでエラー詳細を確認

#### 2. Agent APIからのタイムアウト

**症状**: Agent APIで`Ranker Timeout`ログ

**解決方法**:
- Ranker APIが起動しているか確認
- レスポンス時間を確認（デフォルトタイムアウト: 10秒）
- Agent APIの`RANKER_TIMEOUT_SEC`を増やす

## リンク

- [ML Services README](../README.md)
- [Agent API README](../agent/README.md)
- [プロジェクト全体のREADME](../../README.md)
