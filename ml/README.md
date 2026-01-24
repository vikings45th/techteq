# ML Services

このディレクトリには、firstdownのML関連サービスが含まれています。

## 📋 目次

- [サービス一覧](#サービス一覧)
- [アーキテクチャ](#アーキテクチャ)
- [環境変数](#環境変数)
- [API Key 管理](#api-key-管理)
- [テスト](#テスト)
- [ログ](#ログ)
- [デプロイ](#デプロイ)

## サービス一覧

### Agent API

ルート生成を統括するメインAPIサービス。Maps Routes API、Places API、Ranker、Vertex AIを組み合わせて最適な散歩ルートを提案します。

**主な機能:**
- テーマ別ルート生成（exercise, think, refresh, nature）
- 片道/周回ルート対応（片道は`end_location`必須）
- ルート上のスポット検索（日本語対応、二段階検索+営業時間フィルタ+近傍フィルタ）
- AIによる紹介文・タイトル生成（Vertex AI）
- ナビ用代表点`nav_waypoints`の生成（polyline由来の代表点のみ、周回時は始終点を一致）
- フォールバック機能（外部API障害時も簡易ルートを提供）

詳細は [Agent README](./agent/README.md) を参照してください。

### Ranker API

ルート候補をスコアリングしてランキングするAPIサービス。

**主な機能:**
- ルート特徴量に基づくスコアリング
- 複数ルートの並列評価
- 部分的な成功を許容（一部のルートが失敗してもOK）

詳細は [Ranker README](./ranker/README.md) を参照してください。

## アーキテクチャ

```
┌─────────────────┐
│   Agent API     │ (FastAPI)
│  (Orchestrator) │
└──────┬──────────┘
       │
       ├──► Maps Routes API ──► ルート候補生成
       │
       ├──► Places API ──────► スポット検索（日本語対応）
       │                        - 穴場優先＋補完の二段階検索
       │                        - 営業時間フィルタ（屋外は補完時のみ例外）
       │                        - 重複排除（place_id優先、name/latlng補助）
       │                        - 最大5件まで取得（緯度経度つき）
       │
       ├──► Ranker API ──────► ルート評価・ランキング
       │                        - 特徴量ベースのスコアリング
       │                        - スポット多様性/寄り道ペナルティを考慮
       │                        - タイムアウト: 10秒
       │
       ├──► Vertex AI ───────► 紹介文・タイトル生成
       │                        - モデル: gemini-2.5-flash
       │                        - 構造化出力（JSON）
       │                        - 禁止語フィルタ対応
       │                        - フォールバック機能あり
       │
       └──► BigQuery ────────► ログ・分析データ保存
                                - リクエストログ
                                - 提案ログ
                                - フィードバックログ
                                - SQL定義: `ml/agent/bq/`
```

### 処理フロー

1. **ルート候補生成**: Maps Routes APIで複数のルート候補を生成（形状バリエーション）
2. **特徴量抽出**: 各ルート候補から特徴量を計算
3. **ルート評価**: Ranker APIでスコアリング
4. **最適ルート選択**: スコアが最も高いルートを選択
5. **スポット検索**: ルート上の25/50/75%地点から二段階検索（営業時間フィルタ）
6. **近傍フィルタ**: ルートから近いスポットに絞り込み
7. **紹介文・タイトル生成**: Jinjaテンプレート + 構造化出力で生成
8. **nav_waypoints生成**: polyline簡略化のみ → 最大10点
9. **レスポンス返却**: ルート情報、スポット、紹介文、タイトルを返却

### フォールバック機能

外部APIが失敗した場合でも、簡易ルートを提供します：

- **Maps Routes API失敗**: 開始地点を中心としたダミーポリラインを生成
- **Ranker API失敗**: 最初のルート候補を選択
- **Vertex AI失敗**: テンプレートベースの紹介文・タイトルを使用

## 環境変数

各サービスの環境変数については、各サービスのREADMEを参照してください。

- [Agent API 環境変数](./agent/README.md#環境変数)
- [Ranker API 環境変数](./ranker/README.md)

### 共通設定

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `MAPS_API_KEY` | Google Maps Platform API Key | Agent APIのみ |
| `VERTEX_PROJECT` | Google Cloud Project ID | Agent APIのみ |
| `VERTEX_LOCATION` | Vertex AI リージョン | Agent APIのみ |
| `VERTEX_FORBIDDEN_WORDS` | 禁止ワード（カンマ区切り） | Agent APIのみ |
| `PLACES_RADIUS_M` | Places APIの検索半径（m） | Agent APIのみ |
| `PLACES_MAX_RESULTS` | 1地点あたりの最大件数 | Agent APIのみ |
| `PLACES_SAMPLE_POINTS_MAX` | 検索地点数（サンプル点の上限） | Agent APIのみ |
| `SPOT_MAX_DISTANCE_M` | ルートからの最大距離（m） | Agent APIのみ |
| `SPOT_MAX_DISTANCE_M_RELAXED` | 緩和時の最大距離（m） | Agent APIのみ |
| `SPOT_MAX_DISTANCE_M_FALLBACK` | 追加緩和時の最大距離（m） | Agent APIのみ |

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
- 禁止ワード: `VERTEX_FORBIDDEN_WORDS` を使用（カンマ区切り）

## テスト

### Agent API テスト

`test_generate_api.sh`スクリプトを使用して、4つのテーマでルート生成をテストできます。

```bash
cd ml/agent

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
- 片道テスト時は`end_location`が必須
- 結果をJSON形式で出力（`jq`で整形）

**前提条件:**
- `curl`: HTTPリクエスト用
- `jq`: JSON整形用（オプション）

### Ranker API テスト

```bash
cd ml/ranker
python test_ranker.py
```

詳細は [Ranker README](./ranker/README.md) を参照してください。

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
- `route_proposal`: 提案ログ（選択されたルート、使用ツール、フォールバック情報など）
- `route_feedback`: フィードバックログ（評価、リクエストIDなど）

**データセット:** `firstdown_mvp`（デフォルト）

**SQL定義:** `ml/agent/bq/` に各種SQL（テーブル/ビュー定義）を配置

## デプロイ

各サービスはCloud Runにデプロイされます。設定は`.github/workflows/`を参照してください。

### デプロイトリガー

- **Agent API**: `ml/agent/**` への変更を検知
- **Ranker API**: `ml/ranker/**` への変更を検知

### Agent API リソース設定

- **リージョン**: `asia-northeast1`
- **Timeout**: 300秒（5分）
- **Memory**: 2Gi
- **CPU**: 2
- **Concurrency**: 10

詳細は [Agent README](./agent/README.md#デプロイ) を参照してください。

### Ranker API リソース設定

詳細は [Ranker README](./ranker/README.md) を参照してください。

### デプロイワークフロー

1. GitHub Actionsがコード変更を検知
2. Dockerイメージをビルド
3. Artifact Registryにプッシュ
4. Cloud Runにデプロイ
5. 環境変数を設定（GitHub Secretsから）

### 必要なGCPリソース

1. **Cloud Run**: サービス実行環境
2. **Artifact Registry**: Dockerイメージ保存
3. **BigQuery**: ログ・分析データ保存
4. **サービスアカウント**: Vertex AI認証用

## 開発ガイド

### ローカル開発

#### Agent API

```bash
cd ml/agent
pip install -r requirements.txt
export MAPS_API_KEY="your-api-key"
export VERTEX_PROJECT="your-project-id"
export VERTEX_LOCATION="asia-northeast1"
export RANKER_URL="http://localhost:8080"
uvicorn app.main:app --reload --port 8000
```

#### Ranker API

```bash
cd ml/ranker
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### コード構造

#### Agent API

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

#### Ranker API

```
ml/ranker/
├── app/
│   ├── main.py              # FastAPIアプリケーション、スコアリングロジック
│   ├── schemas.py           # データスキーマ（Pydantic）
│   └── settings.py          # 設定管理
├── Dockerfile
├── requirements.txt
├── README.md
└── test_ranker.py           # テストスクリプト
```

### 主要な機能

#### スポット検索（日本語対応）

- テーマに応じた場所タイプで検索
- ルート上の25/50/75%地点から検索
- 重複排除（place_id優先、なければnameで判定）
- 最大5件まで取得
- ルート近傍でフィルタ（50m → 100m → 250mの順で緩和）
- `name`と`type`を日本語で返却

#### フォールバック機能

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

詳細は各サービスのREADMEを参照してください。

## リンク

- [Agent API README](./agent/README.md)
- [Ranker API README](./ranker/README.md)
- [プロジェクト全体のREADME](../README.md)
