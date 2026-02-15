# Ranker API

ルート候補をスコアリングしてランキングするAPIサービスです。

## 📋 目次

- [概要](#概要)
- [環境変数](#環境変数)
- [API仕様](#api仕様)
- [スコアリングロジック](#スコアリングロジック)
- [実装詳細](#実装詳細)
- [テスト](#テスト)
- [学習とモデル配置](#学習とモデル配置)
- [特徴量重要度と再学習](#特徴量重要度と再学習)
- [タイムアウト](#タイムアウト)
- [デプロイ](#デプロイ)
- [トラブルシューティング](#トラブルシューティング)
- [リンク](#リンク)

## 概要

Ranker APIは、Agent APIから送信されたルート候補を評価し、スコアリングするサービスです。**本番のスコアは、Vertex AI にデプロイしたカスタムモデル（学習済みXGBoost等）のエンドポイントにリクエストを送り、その推論結果を用いてスコアリングしています。** ルールベースのスコアはシャドーで計算してログに保存し、モデル推論失敗時はルールスコアにフォールバックします。

**ストレージ**: 本番の Cloud Run ranker（`ml/ranker`）は GCS を使用しません。Vertex AI カスタム予測コンテナ（`ml/vertex/predictor`）経路でデプロイする場合のみ、モデル・特徴量を GCS から読み込みます。

### 主な機能

- **ルートスコアリング**: Vertex AI Endpoint にデプロイしたカスタムモデルで推論したスコアを本番で使用（特徴量を送り、推論結果でランキング）
- **複数ルートの並列評価**: 最大5件のルートを一度に評価
- **部分的な成功を許容**: 一部のルートが失敗してもOK
- **スコア内訳の提供**: デバッグ用のスコア内訳情報（`model_score`/`rule_score`）
- **シャドウログ**: ルールスコア/モデルスコア/レイテンシをBigQueryへ保存

## 環境変数

### 主な環境変数

| 変数名 | デフォルト値 | 説明 |
|--------|------------|------|
| `MODEL_VERSION` | `unknown` | モデルバージョン（影響確認用） |
| `MODEL_INFERENCE_MODE` | `""` | 推論モード（`vertex` / `xgb` / `stub` / `disabled`）。空なら`MODEL_SHADOW_MODE`へフォールバック |
| `MODEL_SHADOW_MODE` | `xgb` | 互換用の推論モード（`vertex` / `xgb` / `stub` / `disabled`） |
| `MODEL_TIMEOUT_S` | `5.0` | 推論タイムアウト（秒） |
| `MODEL_PATH` | `models/model.xgb.json` | XGBoost成果物パス |
| `MODEL_FEATURES_PATH` | `models/feature_columns.json` | 特徴量カラム定義パス |
| `RANKER_VERSION` | `unknown` | ルール版のバージョン |
| `VERTEX_PROJECT` | なし | Vertex AIのプロジェクトID |
| `VERTEX_LOCATION` | `asia-northeast1` | Vertex AIのリージョン |
| `VERTEX_ENDPOINT_ID` | なし | Vertex AI Endpoint ID |
| `VERTEX_TIMEOUT_S` | `10.0` | Vertex AI推論タイムアウト（秒） |
| `BQ_PROJECT` | なし | BigQueryプロジェクトID |
| `BQ_DATASET` | `firstdown_mvp` | BigQueryデータセット名 |
| `BQ_RANK_RESULT_TABLE` | `rank_result` | BigQueryテーブル名 |

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
        "theme_exercise": 1
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
- `model_score`: モデルスコア（失敗時はnull）

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

- **本番**: Vertex AI Endpoint のモデルスコアでランキング。ルールスコアはシャドー（`breakdown.rule_score` と BigQuery に保存）。モデル失敗時はルールスコアにフォールバック。
- **ルールスコア**: ベース 0.5 ＋ 距離乖離ペナルティ／ループ閉鎖ボーナス／POIボーナス／スポット多様性／寄り道超過ペナルティ（運動・階段・標高は特徴量から外済みのためルールでは加点なし）。0.0–1.0 にクリップ。
- **使用特徴量**: `distance_error_ratio`, `round_trip_req`/`round_trip_fit`, `loop_closure_m`, `park_poi_ratio`, `poi_density`, `spot_type_diversity`, `detour_over_ratio`, `theme_exercise`。詳細は `app/main.py` のスコア計算を参照。

## 実装詳細

### 技術スタック

FastAPI / Pydantic / Python 3.11+。一部ルートのみ失敗時は `failed_route_ids` に記録し、レスポンスはスコア降順・`breakdown` で内訳を返す。

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
│   ├── feature_importance.py # 特徴量重要度の取得（学習済みモデルから）
│   └── requirements.txt     # 学習用依存
├── Dockerfile
├── requirements.txt
├── README.md
└── test_ranker.py           # テストスクリプト
```

## テスト

### テストスクリプト

`cd ml/ranker && python test_ranker.py` で各種特徴量のスコアリングを検証。

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

### BigQuery

`rank_result` の DDL は `ml/ranker/bq/rank_result_shadow.sql`。推論・BQ 書き込み失敗はレスポンスに影響せずログのみ。

## 学習とモデル配置

- **学習データ**: BigQuery の `route_feedback` と `route_candidate` を `ml/agent/bq/training_view.sql` で結合。高評価（rating 4–5）を正例、候補内の一部を弱い負例として回帰（rating）を学習。
- **モデル**: XGBoost 回帰（`reg:pseudohubererror`）。入力は `feature_columns.json`、出力は 0–10 スコア。学習スクリプト: `ml/ranker/training/train_xgb.py`。

### 学習コマンド例

```bash
cd ml/ranker && pip install -r training/requirements.txt
python training/train_xgb.py --project PROJECT --dataset firstdown_mvp --table training_view_poc_aug_v2 --model-version shadow_xgb_v1 --output-dir artifacts
```

成果物: `artifacts/model.xgb.json`, `feature_columns.json`, `metadata.json`。推論用には `models/` にコピーし、Cloud Run ではイメージに同梱。特徴量重要度は `training/feature_importance.py` で確認可能。

## 特徴量重要度と再学習

- **結論**: `training/feature_importance.py` で確認したところ、`elevation_gain_m` / `elevation_density` / `has_stairs` は重要度 0% のため**特徴量から外済み**。レイテンシ削減のため Agent 側で Elevation API と steps 取得をスキップし、Ranker は **18 特徴量**で再学習・デプロイする構成にしている。
- **再学習**: `train_xgb.py` で BigQuery の `training_view` から学習。成果物を `models/` に配置し、Cloud Run は同梱でデプロイ。Vertex 利用時は GCS にアップロードして `ml/ranker/scripts/deploy_vertex.sh` または手動で Predictor をデプロイ（GCS には Compute 用 SA の `roles/storage.objectViewer` を付与）。
- **Vertex に切り替え**: Terraform の `terraform.tfvars` で `ranker_env_model_inference_mode = "vertex"` と `ranker_env_vertex_endpoint_id` を設定して `terraform apply`。再学習後の `--model-version` と `VERSION` を揃えること。

### Vertex AI Online Prediction（カスタムコンテナ）

学習済み XGBoost を `ml/vertex/predictor` でラップし Vertex AI Endpoint にデプロイ。Ranker はそのエンドポイントにリクエストしてスコアを取得し本番ランキングに利用。推論 I/O: 入力 `{"instances":[{feature:value,...}]}`、出力 `{"predictions":[score,...]}`。GCS は `MODEL_GCS_URI` / `FEATURES_GCS_URI` / `METADATA_GCS_URI`。

**前提**: プロジェクト・リージョンは環境に合わせる。Ranker のサービスアカウントに `roles/aiplatform.user`。

#### 1) GCSバケットの作成（初回のみ）

```bash
# バケット名を指定（例: firstdown-vertex-models）
BUCKET_NAME=firstdown-vertex-models
gsutil mb -p firstdown-482704 -l asia-northeast1 gs://${BUCKET_NAME}/
```

#### 2) モデル成果物をGCSに配置

```bash
# バージョン名を指定（例: shadow_xgb_20260211_since_0201）
VERSION=shadow_xgb_20260211_since_0201
BUCKET_NAME=firstdown-vertex-models

# 成果物をGCSにアップロード
gsutil -m cp ml/ranker/models/model.xgb.json gs://${BUCKET_NAME}/ranker/${VERSION}/model.xgb.json
gsutil -m cp ml/ranker/models/feature_columns.json gs://${BUCKET_NAME}/ranker/${VERSION}/feature_columns.json
gsutil -m cp ml/ranker/models/metadata.json gs://${BUCKET_NAME}/ranker/${VERSION}/metadata.json
```

#### 3) Artifact Registryリポジトリの作成（初回のみ）

```bash
# リポジトリ名を指定（例: vertex-predictor）
REPO_NAME=vertex-predictor
gcloud artifacts repositories create ${REPO_NAME} \
  --repository-format=docker \
  --location=asia-northeast1 \
  --project=firstdown-482704
```

#### 4) 推論コンテナをビルドしてArtifact Registryへpush

```bash
PROJECT=firstdown-482704
REPO_NAME=vertex-predictor
TAG=latest  # またはバージョンタグ（例: v1.0.0）

gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/${PROJECT}/${REPO_NAME}/vertex-predictor:${TAG} \
  ml/vertex/predictor
```

#### 5) Vertex AI Modelを作成

```bash
PROJECT=firstdown-482704
BUCKET_NAME=firstdown-vertex-models
VERSION=shadow_xgb_20260211_since_0201
REPO_NAME=vertex-predictor
TAG=latest

gcloud ai models upload \
  --region=asia-northeast1 \
  --project=${PROJECT} \
  --display-name=ranker-xgb-vertex \
  --container-image-uri=asia-northeast1-docker.pkg.dev/${PROJECT}/${REPO_NAME}/vertex-predictor:${TAG} \
  --container-env-vars=MODEL_GCS_URI=gs://${BUCKET_NAME}/ranker/${VERSION}/model.xgb.json,FEATURES_GCS_URI=gs://${BUCKET_NAME}/ranker/${VERSION}/feature_columns.json,METADATA_GCS_URI=gs://${BUCKET_NAME}/ranker/${VERSION}/metadata.json \
  --container-health-route=/health \
  --container-predict-route=/predict
```

アップロード後、`MODEL_ID`をメモしておきます。

#### 6) Vertex AI Endpointを作成

```bash
PROJECT=firstdown-482704

gcloud ai endpoints create \
  --region=asia-northeast1 \
  --project=${PROJECT} \
  --display-name=ranker-xgb-endpoint
```

作成後、`ENDPOINT_ID`をメモしておきます。

#### 7) EndpointにModelをデプロイ

コンテナが GCS からモデルを読むため、**デフォルト Compute 用サービスアカウント**を `--service-account` で指定する（当該 SA にバケットの `roles/storage.objectViewer` を付与しておくこと）。

```bash
PROJECT=firstdown-482704
ENDPOINT_ID=<上記で取得したENDPOINT_ID>
MODEL_ID=<上記で取得したMODEL_ID>
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT} --format="value(projectNumber)")

gcloud ai endpoints deploy-model ${ENDPOINT_ID} \
  --region=asia-northeast1 \
  --project=${PROJECT} \
  --model=${MODEL_ID} \
  --display-name=ranker-xgb-deploy \
  --machine-type=n1-standard-2 \
  --min-replica-count=1 \
  --max-replica-count=2 \
  --service-account=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com
```

#### 8) Ranker の環境変数

`MODEL_INFERENCE_MODE=vertex`, `VERTEX_PROJECT`, `VERTEX_LOCATION`, `VERTEX_ENDPOINT_ID`, `VERTEX_TIMEOUT_S`, `MODEL_VERSION` を設定。

#### 9) 切り戻し

`MODEL_INFERENCE_MODE=disabled`（ルールのみ）または `xgb`（ローカル XGBoost）に変更即可。

#### 10) 動作確認

ローカルで `MODEL_INFERENCE_MODE=vertex` と Vertex 関連変数を設定して `uvicorn app.main:app --reload --port 8080` を起動し、`POST /rank` で `breakdown.model_score` が付与されることを確認。

## タイムアウト

Agent からの呼び出しにはタイムアウトあり（デフォルト 10 秒）。タイムアウト時は Agent 側でヒューリスティックにより最良候補を 1 本選択（詳細は [Agent README](../agent/README.md) のトラブルシューティング参照）。

## デプロイ

Cloud Run にデプロイ。`ml/ranker/**` 変更で GitHub Actions がイメージビルド → Artifact Registry プッシュ → Cloud Run デプロイ。設定は `.github/workflows/deploy-ranker.yml` 参照。要 Cloud Run と Artifact Registry。

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

- [インフラ（IaC）README](../../infra/README.md)
- [ML Services README](../README.md)
- [Agent API README](../agent/README.md)
- [プロジェクト全体のREADME](../../README.md)
