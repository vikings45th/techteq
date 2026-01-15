# Agent API

ルート生成を統括するAPIサービスです。Maps Routes API、Places API、Ranker、Vertex AIを組み合わせて最適な散歩ルートを提案します。

## 📋 目次

- [概要](#概要)
- [環境変数](#環境変数)
- [API Key 管理](#api-key-管理)
- [API仕様](#api仕様)
- [テスト](#テスト)
- [ログ](#ログ)
- [デプロイ](#デプロイ)

## 概要

Agent APIは、ユーザーのリクエストに基づいて最適な散歩ルートを生成するメインサービスです。

### 主な機能

- **テーマ別ルート生成**: 4つのテーマ（exercise, think, refresh, nature）に対応
- **片道/周回ルート**: `round_trip`で周回/片道を切り替え（片道は`end_location`必須）
- **ルート最適化**: Ranker APIを使用したルート品質評価とランキング
- **スポット検索**: ルート上の見どころスポットを自動検索（日本語対応）
- **AI紹介文・タイトル生成**: Vertex AIで紹介文とタイトルを生成
- **ナビ用代表点**: polylineを簡略化して最大10点の`nav_waypoints`を返却
- **フォールバック機能**: 外部API障害時も簡易ルートを提供

### 処理フロー

1. **ルート候補生成**: Maps Routes APIで複数のルート候補を生成
2. **特徴量抽出**: 各ルート候補から特徴量を計算
3. **ルート評価**: Ranker APIでスコアリング
4. **最適ルート選択**: スコアが最も高いルートを選択
5. **スポット検索**: ルート上の25/50/75%地点からスポットを検索（日本語対応）
6. **紹介文・タイトル生成**: Vertex AIで紹介文とタイトルを生成
7. **nav_waypoints生成**: polyline簡略化 → 最大10点を抽出
8. **レスポンス返却**: ルート情報、スポット、紹介文、タイトルを返却

## 環境変数

### 必須環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `MAPS_API_KEY` | Google Maps Platform API Key（Routes API / Places API共通） | `AIza...` |
| `VERTEX_PROJECT` | Google Cloud Project ID（Vertex AI使用時） | `firstdown-482704` |
| `VERTEX_LOCATION` | Vertex AI リージョン | `asia-northeast1` |

### オプション環境変数

| 変数名 | デフォルト値 | 説明 |
|--------|------------|------|
| `RANKER_URL` | `http://ranker:8080` | Ranker APIの内部URL |
| `REQUEST_TIMEOUT_SEC` | `10.0` | 外部API呼び出しのタイムアウト（秒） |
| `RANKER_TIMEOUT_SEC` | `10.0` | Ranker API呼び出しのタイムアウト（秒） |
| `VERTEX_TEXT_MODEL` | `gemini-2.5-flash` | Vertex AIで使用するモデル名 |
| `VERTEX_TEMPERATURE` | `0.3` | Vertex AIの温度パラメータ |
| `VERTEX_MAX_OUTPUT_TOKENS` | `256` | Vertex AIの最大出力トークン数 |
| `VERTEX_TOP_P` | `0.95` | Vertex AIのtop_pパラメータ |
| `VERTEX_TOP_K` | `40` | Vertex AIのtop_kパラメータ |
| `BQ_DATASET` | `firstdown_mvp` | BigQueryデータセット名 |
| `BQ_TABLE_REQUEST` | `route_request` | BigQueryリクエストテーブル名 |
| `BQ_TABLE_CANDIDATE` | `route_candidate` | BigQuery候補テーブル名 |
| `BQ_TABLE_PROPOSAL` | `route_proposal` | BigQuery提案テーブル名 |
| `BQ_TABLE_FEEDBACK` | `route_feedback` | BigQueryフィードバックテーブル名 |
| `FEATURES_VERSION` | `mvp_v1` | 特徴量バージョン |
| `RANKER_VERSION` | `rule_v1` | Rankerバージョン |

## API Key 管理

### Google Maps Platform API Key

**用途:**
- **Routes API**: ルート候補の生成
- **Places API**: ルート上のスポット検索（日本語対応）

**取得方法:**
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 「APIとサービス」→「認証情報」→「認証情報を作成」→「APIキー」
3. 必要なAPIを有効化:
   - Routes API (Directions API v2)
   - Places API (New)

**セキュリティ:**
- Cloud Runの環境変数として設定（GitHub Secrets経由）
- APIキー制限を設定（HTTPリファラー、IPアドレスなど）

**Places APIの言語設定:**
- リクエストに`languageCode: "ja"`を指定して日本語レスポンスを取得
- スポットの`name`と`type`は日本語で返されます

### Vertex AI 認証

**用途:**
- Vertex AI: ルート紹介文の生成

**認証方法:**
- サービスアカウントを使用（Cloud RunのサービスアカウントにVertex AI権限を付与）
- `VERTEX_PROJECT`と`VERTEX_LOCATION`を環境変数で指定

**必要な権限:**
- `aiplatform.endpoints.predict`
- `aiplatform.models.predict`

**使用モデル:**
- デフォルト: `gemini-2.5-flash`
- 温度パラメータ: `0.3`
- 最大出力トークン: `256`

## API仕様

### エンドポイント

#### `POST /route/generate`

ルート生成リクエスト

**注意:**
- `round_trip: true` の場合は `end_location` を無視します
- `round_trip: false` の場合は `end_location` が必須です

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
        "type": "公園"
      }
    ]
  },
  "meta": {
    "fallback_used": false,
    "tools_used": ["maps_routes", "places", "ranker", "vertex_llm"],
    "fallback_reason": null,
    "fallback_details": [],
    "route_quality": {
      "is_fallback": false,
      "distance_match": 0.95,
      "distance_error_km": 0.2,
      "quality_score": 0.9
    }
  }
}
```

**レスポンスフィールド:**
- `route.route_id`: ルートID（UUID）
- `route.polyline`: エンコードされたpolyline文字列（地図表示用）
- `route.distance_km`: 距離（km）
- `route.duration_min`: 所要時間（分）
- `route.title`: ルートのタイトル（日本語）
- `route.summary`: ルートの紹介文（日本語）
- `route.nav_waypoints`: ナビ用の代表点（最大10点）
- `route.spots`: 見どころスポットのリスト（日本語）
  - `name`: スポット名（日本語）
  - `type`: スポットタイプ（日本語、例: "公園", "カフェ"）
- `meta.fallback_used`: フォールバックが使用されたかどうか
- `meta.tools_used`: 使用したツールのリスト
- `meta.fallback_reason`: フォールバック理由（カンマ区切り）
- `meta.route_quality`: ルート品質情報

**テーマ:**
- `exercise`: 運動やエクササイズに適したルート
- `think`: 思考や頭の整理に適したルート
- `refresh`: 気分転換やリフレッシュに適したルート
- `nature`: 自然や緑を楽しむルート

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

**レスポンス例:**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted"
}
```

#### `GET /health`

ヘルスチェック

**レスポンス例:**
```json
{
  "status": "ok"
}
```

### フォールバック機能

外部APIが失敗した場合でも、簡易ルートを提供します：

- **Maps Routes API失敗**: 開始地点を中心としたダミーポリラインを生成
- **Ranker API失敗**: 最初のルート候補を選択
- **Vertex AI失敗**: テンプレートベースの紹介文・タイトルを使用

フォールバック情報は`meta.fallback_used`と`meta.fallback_reason`に記録されます。

## テスト

### APIテストスクリプト

`test_generate_api.sh`スクリプトを使用して、4つのテーマでルート生成をテストできます。

```bash
# 環境変数を設定
export AGENT_URL="http://localhost:8000"
# または本番環境
export AGENT_URL="https://agent-203786374782.asia-northeast1.run.app"

# テスト実行
bash test_generate_api.sh
```

**テスト内容:**
- 4つのテーマ（exercise, think, refresh, nature）でテスト
- ランダムな開始地点（東京周辺）と距離（1.0-5.0km）でリクエスト
- `round_trip: true`, `debug: false` で固定
- フィードバック評価は`FEEDBACK_RATING`未指定時に1〜5でランダム
- 結果をJSON形式で出力（`jq`で整形）

**前提条件:**
- `curl`: HTTPリクエスト用
- `jq`: JSON整形用（オプション）

**出力例:**
```
🚀 Generate API テストスクリプト
API URL: http://localhost:8000
テスト対象テーマ: exercise think refresh nature

============================================================
テーマ: exercise
開始地点: (35.681234, 139.767123)
距離: 3.2km
往復ルート: true
リクエストID: test-1234567890-12345
============================================================
✅ 成功 (HTTP 200)

{
  "request_id": "test-1234567890-12345",
  "route": {
    "polyline": "...",
    "distance_km": 3.2,
    "duration_min": 45,
    "summary": "...",
    "spots": [
      {
        "name": "代々木公園",
        "type": "公園"
      }
    ]
  },
  ...
}
```

### ローカル開発

```bash
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

## ログ

### Cloud Logging での追跡

すべてのログに`request_id`を含めることで、1つのリクエストを追跡可能です。

**ログ形式:**
```
[Component] request_id={request_id} message...
```

**主要なログタグ:**
- `[Routes API Error]`: Maps Routes APIエラー
- `[Places]`: Places API成功
- `[Places Error]`: Places APIエラー
- `[Ranker Timeout]`: Rankerタイムアウト
- `[Ranker Error]`: Rankerエラー
- `[Vertex LLM Error]`: Vertex AIエラー
- `[Fallback Polyline Error]`: Fallback処理エラー

**Cloud Loggingでの検索例:**
```
resource.type="cloud_run_revision"
jsonPayload.request_id="your-request-id"
```

### BigQuery へのログ保存

以下のテーブルにログが保存されます：

- `route_request`: リクエストログ（テーマ、距離、開始地点など）
- `route_candidate`: 候補ログ（特徴量、順位、フォールバック情報など）
- `route_proposal`: 提案ログ（選択されたルート、使用ツール、フォールバック情報など）
- `route_feedback`: フィードバックログ（評価、リクエストIDなど）

学習用ビュー:

- `training_view`: `route_candidate` と `route_feedback` を `request_id` + `route_id` でJOINした学習入力
  - ビュー定義: `ml/agent/bq/training_view.sql`
  - 学習入力は `SELECT * FROM training_view`
  - リーク対策として `chosen_flag` / `shown_rank` など結果依存列は除外

**データセット:** `firstdown_mvp`（デフォルト）

## デプロイ

Cloud Runにデプロイされます。設定は`.github/workflows/deploy-agent.yml`を参照してください。

### リソース設定

- **リージョン**: `asia-northeast1`
- **Timeout**: 300秒（5分）
- **Memory**: 2Gi
- **CPU**: 2
- **Concurrency**: 10

### デプロイワークフロー

1. GitHub Actionsが`ml/agent/**`への変更を検知
2. Dockerイメージをビルド
3. Artifact Registryにプッシュ
4. Cloud Runにデプロイ
5. 環境変数を設定（GitHub Secretsから）

### 必要なGCPリソース

1. **Cloud Run**: サービス実行環境
2. **Artifact Registry**: Dockerイメージ保存
3. **BigQuery**: ログ・分析データ保存
4. **サービスアカウント**: Vertex AI認証用

## コード構造

```
ml/agent/
├── app/
│   ├── main.py              # FastAPIアプリケーション、ルート生成ロジック
│   ├── schemas.py           # データスキーマ（Pydantic）
│   ├── settings.py          # 設定管理
│   └── services/
│       ├── maps_routes_client.py  # Maps Routes APIクライアント
│       ├── places_client.py       # Places APIクライアント（日本語対応）
│       ├── ranker_client.py       # Ranker APIクライアント
│       ├── vertex_llm.py          # Vertex AIクライアント
│       ├── feature_calc.py        # 特徴量計算
│       ├── fallback.py            # フォールバック処理
│       ├── polyline.py            # Polyline処理
│       └── bq_writer.py           # BigQuery書き込み
├── Dockerfile
├── requirements.txt
├── README.md
└── test_generate_api.sh     # APIテストスクリプト
```

## 主要な機能

### スポット検索（日本語対応）

- テーマに応じた場所タイプで検索
- ルート上の25/50/75%地点から検索
- 重複排除（place_id優先、なければnameで判定）
- 最大5件まで取得
- `name`と`type`を日本語で返却
  - `name`: Places APIから取得（`languageCode: "ja"`で日本語化）
  - `type`: 英語タイプを日本語に変換（例: "park" → "公園"）

### フォールバック機能

外部APIが失敗した場合のフォールバック処理：

1. **Maps Routes API失敗**: ダミーポリラインを生成
2. **Ranker API失敗**: 最初のルート候補を選択
3. **Vertex AI失敗**: テンプレートベースの紹介文を使用

フォールバック情報は`meta.fallback_used`と`meta.fallback_reason`に記録されます。

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

**原因**:
- Maps Routes APIの失敗
- Ranker APIの失敗
- Vertex AIの失敗

**確認方法**:
- ログで `fallback_reason` を確認
- 各サービスのヘルスチェックを実行

## リンク

- [ML Services README](../README.md)
- [Ranker API README](../ranker/README.md)
- [プロジェクト全体のREADME](../../README.md)
