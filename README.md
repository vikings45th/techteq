# tekuteq

散歩ルートを自動生成する Web アプリケーション。テーマに応じた最適な散歩コースを提案します。

## 概要

tekuteq は、**ユーザーの意思決定を減らし、入力を少なく**する散歩提案サービスです。自分でコースや距離を選ぶのではなく、サービス側が AI を活用して「今の気分に合う散歩を一つだけ」提案します。Google Cloud Vertex AI を活用し、紹介文・タイトル生成とルート品質のランキングを行っています。

### 主な機能

**フロントエンド**
- **散歩提案チャット**: ランディングでチャットを開くと AI が自動で散歩を一つ提案。天候・日時を考慮したテーマ・距離の提案、「ちょっと違う気分」で再提案。
- **一つだけ提案**: 複数候補から選ばせず、サービスがルートを一つに絞って提示する UI。
- **入力を少なくしたフロー**: テーマや距離をユーザーが直接入力せず、チャットで答えるだけでルート候補まで進める。
- **Google マップへの遷移**: 生成したルートから Google マップ（アプリまたは Web）に遷移し、実際のルート案内（ナビ）を利用できる。

**バックエンド**
- **Vertex AI（Gemini）**: ルートの紹介文・タイトルを構造化出力で生成。ランディングのテーマ・距離提案。
- **Vertex AI（カスタム推論）**: ルート候補の品質を ML モデルでスコアリングし、ランキングで最適なルートを選定。
- **Maps Routes API / Places API**: ルート候補の逐次的生成、スポット検索、形状多様化・距離フィルタ・フォールバック。

### 技術スタック

Google Cloud Vertex AI（Gemini, カスタム推論 Endpoint）/ Nuxt.js 4 / FastAPI / Google Maps Platform (Routes, Places) / Cloud Run / BigQuery / Terraform / GitHub Actions

## アーキテクチャ

```
Web (Nuxt) → Agent API (FastAPI) → Ranker API, Vertex AI, Maps API, BigQuery
```

- **Web** (`web/`): フロントエンド。Nuxt のサーバー API で Agent を呼び出し。
- **Agent** (`ml/agent/`): ルート生成のオーケストレーション（LangGraph）。
- **Ranker** (`ml/ranker/`): ルート候補のスコアリング（Vertex AI Endpoint またはローカル推論）。

## クイックスタート

**前提**: Python 3.11+, Node.js 18+, GCP アカウント, Maps API Key

```bash
# 1. Agent API（port 8000）
cd ml/agent && pip install -r requirements.txt
export MAPS_API_KEY="your-key" VERTEX_PROJECT="your-project" VERTEX_LOCATION="asia-northeast1" RANKER_URL="http://localhost:8080"
uvicorn app.main:app --reload --port 8000

# 2. Ranker API（port 8080）※別ターミナル
cd ml/ranker && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8080

# 3. Web（port 3000）※別ターミナル
cd web && npm install && npm run dev
```

ブラウザで http://localhost:3000 を開き、テーマ・開始地点・距離を入力してルート生成を試せます。

各サービスの環境変数・詳細手順は各ディレクトリの README を参照してください。

## プロジェクト構造

```
tekuteq/
├── .github/workflows/   # CI/CD（Agent / Ranker の Cloud Run デプロイ）
├── infra/               # Terraform（GCP リソース・IAM・Cloud Run 定義）
├── ml/
│   ├── agent/           # ルート生成 API（FastAPI）
│   ├── ranker/          # ルート評価 API（FastAPI）
│   └── vertex/predictor # Vertex AI カスタム推論コンテナ
└── web/                 # フロントエンド（Nuxt 4）
```

## ドキュメント

| 対象 | 扱うトピック | 参照先 |
|------|--------------|--------|
| Agent | API 仕様（リクエスト/レスポンス）、ルート生成オーケストレーション、環境変数、BigQuery、ログ・トレース、トラブルシューティング | [ml/agent/README.md](./ml/agent/README.md) |
| Ranker | API 仕様、ルート評価・スコアリング、環境変数、Vertex 推論、トラブルシューティング | [ml/ranker/README.md](./ml/ranker/README.md) |
| Infra | デプロイ、Terraform、Cloud Run 定義、認証・IAM、GCP リソース、GitHub Secrets | [infra/README.md](./infra/README.md) |
| Web | フロント開発、サーバー API（ルート生成・フィードバック・Gemini 提案）、環境変数 | [web/README.md](./web/README.md) |

ML 全体の BigQuery テーブル定義・学習パイプラインなどは [ml/README.md](./ml/README.md) を参照。
