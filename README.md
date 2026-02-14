# firstdown

散歩ルートを自動生成するWebアプリケーション。テーマに応じた最適な散歩コースを提案します。

## 📋 目次

- [概要](#概要)
- [アーキテクチャ](#アーキテクチャ)
- [プロジェクト構造](#プロジェクト構造)
- [セットアップ](#セットアップ)
- [使用方法](#使用方法)
- [API仕様](#api仕様)
- [デプロイ](#デプロイ)
- [開発ガイド](#開発ガイド)
- [トラブルシューティング](#トラブルシューティング)
- [ライセンス](#ライセンス)
- [コントリビューション](#コントリビューション)
- [リンク](#リンク)

## 概要

firstdownは、ユーザーの好みに応じて最適な散歩ルートを生成するサービスです。

### 主な機能

- **気分・モードに応じたルート生成**: 4モード（exercise, think, refresh, nature）に合わせてルートを提案
- **AIによる紹介文・タイトル生成**: Vertex AI + 構造化出力で安定した文面を生成
- **スポット検索**: 二段階検索（穴場キーワード → テーマに合った場所タイプ）+ ルート近傍フィルタ
- **ルート最適化**: 機械学習によるルート品質評価とランキング（Vertex AI Endpoint推論）
- **ルート形状の多様化**: 直線/円/蛇行など複数形状の候補を生成
- **フォールバック機能**: 4種類（Routes/Ranker/Vertex 失敗・無効ルート検出）に対応。簡易ルートやテンプレート文で応答し、`meta.fallback_details` で理由を返却

### 技術スタック

- **フロントエンド**: Nuxt.js 4, Vue 3, Nuxt UI
- **バックエンド**: FastAPI (Python)
- **ML/AI**: Vertex AI (Gemini), ルートランキングモデル
- **外部API**: Google Maps Platform (Routes API, Places API)
- **インフラ**: Google Cloud Run, BigQuery。GCP リソースの定義は Terraform（[infra/](infra/README.md)）で管理
- **CI/CD**: GitHub Actions

## アーキテクチャ

```
┌─────────────┐
│   Web App   │ (Nuxt.js)
│  (Frontend) │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│   Agent API     │ (FastAPI)
│  (Orchestrator) │
└──────┬──────────┘
       │
       ├──► Maps Routes API ──► ルート候補の蓄積的生成（形状多様化・距離フィルタ・短距離補正・再試行・閾値で早期終了）
       ├──► Places API ──────► スポット検索
       ├──► Ranker API ──────► ルート評価
       │                         └──► Vertex AI Endpoint（ランキング用推論）
       ├──► Vertex AI ───────► 紹介文・タイトル生成
       └──► BigQuery ────────► ログ・分析
```

### サービス構成

1. **Web App** (`web/`): ユーザー向けフロントエンド（Nuxt サーバーAPI: ルート生成プロキシ・フィードバック・ランディング用AI提案）
2. **Agent API** (`ml/agent/`): ルート生成を統括するメインAPI
3. **Ranker API** (`ml/ranker/`): ルート候補をスコアリングするサービス

## プロジェクト構造

```
firstdown/
├── .github/
│   └── workflows/          # CI/CD
│       ├── deploy-agent.yml
│       └── deploy-ranker.yml
├── infra/                  # インフラ（IaC）
│   ├── README.md           # 方針・使い方・GCPサービスとIaCの対応
│   └── terraform/          # Terraform（API有効化、AR、BQ、IAM、Cloud Run定義）
├── ml/
│   ├── agent/              # ルート生成API（FastAPI）
│   │   ├── app/
│   │   │   ├── main.py     # エンドポイント定義
│   │   │   ├── graph.py    # ルート生成オーケストレーション（LangGraph）
│   │   │   ├── schemas.py
│   │   │   ├── settings.py
│   │   │   ├── utils.py
│   │   │   ├── prompts/    # Vertex AI用Jinja
│   │   │   └── services/   # maps_routes_client, places_client, ranker_client,
│   │   │                   # vertex_llm, feature_calc, fallback, polyline, bq_writer, http_client
│   │   ├── bq/             # BigQuery用DDL・ビュー（route_*.sql, training_view.sql 等）
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── README.md
│   │   └── test_generate_api.sh
│   ├── ranker/             # ルート評価API（FastAPI）
│   │   ├── app/            # main.py, model_scoring.py, bq_logger.py, schemas.py, settings.py
│   │   ├── bq/             # rank_result_shadow.sql
│   │   ├── training/       # train_xgb.py（学習スクリプト）
│   │   ├── artifacts/      # 学習成果物出力先
│   │   ├── models/         # 推論用成果物（model.xgb.json 等）
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── README.md
│   │   └── test_ranker.py
│   └── vertex/
│       └── predictor/      # Vertex AI カスタム推論コンテナ（Ranker用）
│           ├── app.py
│           ├── Dockerfile
│           └── requirements.txt
└── web/                    # フロントエンド（Nuxt 4）
    ├── app/                # pages/, layouts/, composables/, types/, app.vue, app.config.ts
    ├── server/api/         # fetch-ai, route-feedback, gemini
    ├── assets/
    ├── public/
    ├── nuxt.config.ts
    ├── Dockerfile
    ├── package.json
    └── README.md
```

## セットアップ

### 前提条件

- Python 3.11+
- Node.js 18+
- Docker (オプション)
- Google Cloud Platform アカウント
- Google Maps Platform API Key

### ローカル開発環境

#### 1. Agent API のセットアップ

```bash
cd ml/agent

# 依存関係のインストール
pip install -r requirements.txt

# 環境変数の設定
export MAPS_API_KEY="your-api-key"
export VERTEX_PROJECT="your-project-id"
export VERTEX_LOCATION="asia-northeast1"
export RANKER_URL="http://localhost:8080"

# サーバー起動
uvicorn app.main:app --reload --port 8000
```

詳細は [ml/agent/README.md](./ml/agent/README.md) を参照してください。

#### 2. Ranker API のセットアップ

```bash
cd ml/ranker

# 依存関係のインストール
pip install -r requirements.txt

# サーバー起動
uvicorn app.main:app --reload --port 8080
```

詳細は [ml/ranker/README.md](./ml/ranker/README.md) を参照してください。

#### 3. Web App のセットアップ

```bash
cd web

# 依存関係のインストール
npm install

# 開発サーバー起動
npm run dev
```

詳細は [web/README.md](./web/README.md) を参照してください。

### 環境変数

各サービスの環境変数については、各サービスのREADMEを参照してください。

- [Agent API 環境変数](./ml/agent/README.md#環境変数)
- [Ranker API 環境変数](./ml/ranker/README.md)

## 使用方法

### APIテスト

Agent APIのテストスクリプトを使用して、4つのテーマでルート生成をテストできます。

```bash
cd ml/agent

# 環境変数を設定
export AGENT_URL="http://localhost:8000"
# または本番環境
export AGENT_URL="https://agent-203786374782.asia-northeast1.run.app"

# テスト実行
bash test_generate_api.sh
```

このスクリプトは以下を実行します：
- 4つのテーマ（exercise, think, refresh, nature）でテスト
- ランダムな開始地点と距離でリクエスト
- 結果をJSON形式で出力

### Web App の使用

1. 開発サーバーを起動: `cd web && npm run dev`
2. ブラウザで `http://localhost:3000` にアクセス
3. ルート生成フォームで以下を入力：
   - テーマ選択
   - 開始地点（緯度・経度）
   - 距離（km）
   - 往復ルートの有無

## API仕様

### Agent API

#### `POST /route/generate`

ルート生成リクエスト

**注意:**
- `round_trip: true` の場合は `end_location` を無視します（送信は可）
- `round_trip: false` の場合は `end_location` が必須です
- 片道で直線距離が短い場合は、目標距離に合わせて回り道します
- `nav_waypoints` は polyline 由来の代表点で構成され、周回ルートでは始終点が一致します

**リクエスト例（周回）:**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "theme": "exercise",
  "distance_km": 3.0,
  "start_location": {
    "lat": 35.6812,
    "lng": 139.7671
  },
  "end_location": {
    "lat": 35.6896,
    "lng": 139.6917
  },
  "round_trip": true,
  "debug": false
}
```

**リクエスト例（片道）:**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "theme": "refresh",
  "distance_km": 3.0,
  "start_location": {
    "lat": 35.6812,
    "lng": 139.7671
  },
  "end_location": {
    "lat": 35.6896,
    "lng": 139.6917
  },
  "round_trip": false,
  "debug": false
}
```

**レスポンス例:**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "route": {
    "route_id": "e3b0c442-98fc-1c14-9afb-3c2e4f7a1d0b",
    "polyline": "encoded_polyline_string",
    "distance_km": 3.2,
    "duration_min": 45,
    "title": "木陰を抜ける川沿いウォーク",
    "summary": "運動に適した散歩ルートです...",
    "nav_waypoints": [
      {"lat": 35.6812, "lng": 139.7671},
      {"lat": 35.6840, "lng": 139.7702}
    ],
    "spots": [
      {
        "name": "代々木公園",
        "type": "公園",
        "lat": 35.6717,
        "lng": 139.6949
      }
    ]
  },
  "meta": {
    "fallback_used": false,
    "tools_used": ["maps_routes", "places", "ranker", "vertex_llm"],
    "route_quality": {
      "is_fallback": false,
      "distance_match": 0.95,
      "distance_error_km": 0.2,
      "quality_score": 0.9
    }
  }
}
```

#### `POST /route/feedback`

フィードバック送信

**リクエスト例:**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "route_id": "e3b0c442-98fc-1c14-9afb-3c2e4f7a1d0b",
  "rating": 5
}
```

#### `GET /health`

ヘルスチェック

詳細は [ml/agent/README.md](./ml/agent/README.md#api仕様) を参照してください。

### Ranker API

詳細は [ml/ranker/README.md](./ml/ranker/README.md#api仕様) を参照してください。

## デプロイ

### Cloud Run へのデプロイ

Agent API と Ranker API は GitHub Actions 経由で自動デプロイされます。Web App（web）のデプロイは別ワークフローまたは手動で実施している場合があります。GCP リソースの定義は [infra/README.md](infra/README.md) を参照してください。

#### デプロイトリガー

- **Agent API**: `ml/agent/**` への変更を検知
- **Ranker API**: `ml/ranker/**` への変更を検知

#### デプロイ設定

- **リージョン**: `asia-northeast1`
- **タイムアウト**: 300秒（Agent API）
- **メモリ**: 2Gi（Agent API）
- **CPU**: 2（Agent API）

詳細は `.github/workflows/` を参照してください。

### 必要なGCPリソース

API 有効化・Artifact Registry・BigQuery データセット・サービスアカウントと IAM は [infra/terraform/](infra/README.md) で Terraform 定義済み。Cloud Run へのデプロイは GitHub Actions のまま。

1. **Cloud Run**: サービス実行環境
2. **Artifact Registry**: Docker イメージ保存
3. **BigQuery**: ログ・分析データ保存。データセット `firstdown_mvp` に、リクエスト・候補・提案・フィードバック・ランク結果用のテーブルと学習用ビューを配置。テーブル定義と用途は [ml/README.md](./ml/README.md#bigquery-テーブル定義と用途) および [ml/agent/README.md](./ml/agent/README.md#bigquery-テーブル定義と用途) を参照。
4. **サービスアカウント**: Vertex AI 認証用

### 環境変数の設定

GitHub Secretsに以下を設定してください：

- `GCP_SA_KEY`: GCPサービスアカウントキー（JSON）
- `MAPS_API_KEY`: Google Maps Platform API Key

## 開発ガイド

### コーディング規約

- **Python**: PEP 8準拠、型ヒント使用
- **TypeScript/JavaScript**: ESLint準拠
- **コミットメッセージ**: 明確で簡潔に

### テスト

#### Agent API テスト

```bash
cd ml/agent
bash test_generate_api.sh
```

#### Ranker API テスト

```bash
cd ml/ranker
python test_ranker.py
```

### ログ

すべてのログに`request_id`を含めることで、1つのリクエストを追跡可能です。

**ログ形式:**
```
[Component] request_id={request_id} message...
```

**Cloud Loggingでの検索例:**
```
resource.type="cloud_run_revision"
jsonPayload.request_id="your-request-id"
```

運用ログは Cloud Logging に保存。長期保存する場合は、ログシンクで GCS にエクスポートし、バケットのライフサイクルで Nearline/Coldline に移すと料金を抑えられる（必要になったら Terraform でシンク・バケットを追加可）。

### 主要なログタグ

- `[Routes API Error]`: Maps Routes APIエラー
- `[Places]`: Places API成功
- `[Places Error]`: Places APIエラー
- `[Ranker Timeout]`: Rankerタイムアウト
- `[Ranker Error]`: Rankerエラー
- `[Vertex LLM Error]`: Vertex AIエラー
- `[Fallback Polyline Error]`: Fallback処理エラー

## トラブルシューティング

### よくある問題

#### 1. API Key エラー

**症状**: `MAPS_API_KEY is not configured` エラー

**解決方法**:
- 環境変数 `MAPS_API_KEY` が設定されているか確認
- Google Cloud ConsoleでAPIが有効化されているか確認
- API Keyの制限設定を確認

#### 2. Vertex AI 認証エラー

**症状**: `Permission denied` エラー

**解決方法**:
- サービスアカウントに `aiplatform.endpoints.predict` 権限があるか確認
- `VERTEX_PROJECT` と `VERTEX_LOCATION` が正しく設定されているか確認

#### 3. Ranker API タイムアウト

**症状**: `Ranker Timeout` ログ

**解決方法**:
- Ranker APIが起動しているか確認
- `RANKER_URL` が正しく設定されているか確認
- `RANKER_TIMEOUT_SEC` を増やす（デフォルト: 10秒）

#### 4. フォールバックルートが生成される

**症状**: `fallback_used: true` が返される

**原因**（理由コード）:
- `maps_routes_failed`: Maps Routes API の失敗
- `ranker_failed`: Ranker API の失敗・タイムアウト
- `vertex_llm_failed`: Vertex AI の失敗（紹介文・タイトルのみテンプレートに差し替え）
- `invalid_route_detected`: 選択されたルートが無効（距離極小や polyline 不正）だったためダミーに差し替え

**確認方法**:
- レスポンスの `meta.fallback_reason` および `meta.fallback_details` で理由を確認
- ログで `fallback_reason` を検索
- 各サービスのヘルスチェックを実行

### デバッグモード

APIリクエストで `debug: true` を設定すると、追加のデバッグ情報が返されます：

```json
{
  "request_id": "...",
  "theme": "exercise",
  "distance_km": 3.0,
  "start_location": {...},
  "round_trip": true,
  "debug": true
}
```

レスポンスに以下が含まれます：
- `meta.plan`: 処理ステップのリスト
- `meta.retry_policy`: リトライポリシー
- `meta.debug`: 詳細なデバッグ情報

## ライセンス

[ライセンス情報を記載]

## コントリビューション

[コントリビューションガイドラインを記載]

## リンク

- [インフラ（IaC）README](./infra/README.md)
- [Agent API README](./ml/agent/README.md)
- [Ranker API README](./ml/ranker/README.md)
- [Web App README](./web/README.md)
- [ML Services README](./ml/README.md)
