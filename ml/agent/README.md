# Agent API

ルート生成を統括するAPIサービスです。Maps Routes API、Places API、Ranker、Vertex AIを組み合わせて最適な散歩ルートを提案します。

## 📋 目次

- [概要](#概要)
- [主要な機能](#主要な機能)
- [ローカル開発・テスト](#ローカル開発・テスト)
- [API仕様](#api仕様)
- [環境変数](#環境変数)
- [API Key 管理](#api-key-管理)
- [外部連携](#外部連携)
- [ログ](#ログ)
- [デプロイ](#デプロイ)
- [コード構造](#コード構造)
- [トラブルシューティング](#トラブルシューティング)
- [リンク](#リンク)

## 概要

Agent APIは、ユーザーのリクエストに基づいて最適な散歩ルートを生成するメインサービスです。

### 主な機能

- **気分・モードに応じたルート生成**: ユーザーが選んだ4モード（exercise / think / refresh / nature）に合わせてルートを提案（内部ではテーマ別にルート・スポットを最適化）
- **片道/周回ルート**: `round_trip`で周回/片道を切り替え（片道は`end_location`必須）
- **ルート最適化**: 逐次的ルート生成（1本ずつ生成し、閾値・最低本数で早期終了）ののち、候補を一括で Ranker API に送ってモデルスコアでランキング（ルールはシャドー）
- **スポット検索**: 二段階検索（穴場キーワード → テーマに合った場所タイプ、結果なし時はタイプ指定なしで再検索）+ ルート近傍フィルタ（距離で絞り込み・緩和）
- **AI紹介文・タイトル生成**: Jinjaテンプレート + 構造化出力で安定生成
- **ナビ用代表点**: polyline由来の代表点のみで最大10点の`nav_waypoints`（周回時は始終点一致）
- **フォールバック機能**: 外部API障害時も簡易ルートを提供
- **フィードバック収集**: `POST /route/feedback` で学習用フィードバックを蓄積

### 処理フロー

1. **ルート候補の逐次的生成**: 候補を1本ずつ Maps Routes API で生成。各ルートをヒューリスティック（距離乖離など）で簡易評価し、**閾値（SCORE_THRESHOLD）を超えていて**かつ**最低本数（MIN_ROUTES）に達した**時点で打ち切り（早期終了）。最大 MAX_ROUTES 本まで（従来の「5本一括生成→一括スコアリング」から、逐次的生成に変更）
2. **特徴量抽出**: 揃った候補それぞれから特徴量を計算
3. **ルート評価**: 候補を一括で Ranker API に送り、モデルスコアでスコアリング
4. **最適ルート選択**: スコアが最も高いルートを選択
5. **スポット検索**: ルート上の25/50/75%地点から二段階検索（穴場→テーマ別タイプ）+ ルート近傍フィルタ
6. **紹介文・タイトル生成**: Vertex AIで紹介文とタイトルを生成
7. **nav_waypoints生成**: polyline簡略化のみ → 最大10点（周回時は始終点一致）
8. **レスポンス返却**: ルート情報、スポット、紹介文、タイトルを返却

### ルート候補生成の詳細（Maps Routes API まわり）

- **目的地の多様化**（`compute_route_dests`）  
  - **周回**: 方位角を6方向で回転・シャッフルし、形状バリエーション（円に近いループ・三角ループ・アウト&バック・蛇行）で waypoints を生成。距離に応じて半径・ステップを変える。  
  - **片道（end_location あり）**: 開始〜終了の直線距離が目標未満なら、回り道用の waypoints を挟んで目標距離に近づける。終了が開始に極端に近い（<0.05km）場合は end を無視しオフセット目的地にフォールバック。  
  - **片道（end なし）**: 方位角ごとに開始点からオフセットした1点を目的地とする。
- **距離フィルタ**: 各候補について `|実距離−目標|/目標`（目標はユーザー指定の `original_target_km`）を計算し、`ROUTE_DISTANCE_ERROR_RATIO_MAX`（短距離時は 0.2）を超えるものは採用しない。
- **短距離の扱い**: 目標が `SHORT_DISTANCE_MAX_KM` 以下なら、誤差比率を 0.2 に厳格化。さらに `SHORT_DISTANCE_TARGET_RATIO` で事前に目標距離を補正して Routes API に渡す。1試行目で候補が0件のときは、観測した「目標に最も近い距離」に基づき目標を再計算して最大 `ROUTE_DISTANCE_RETRY_MAX + 1` 回まで再試行する。
- **無効候補のスキップ**: 実距離が 0.01km 以下、または polyline が空・不正値の候補はスキップ（カウントせず次の目的地でルート取得を続ける）。

### プロンプトテンプレート

- `app/prompts/description.jinja`: 紹介文の制約（JSON形式、文字数、句点など）
- `app/prompts/title.jinja`: タイトルの制約（JSON形式、文字数、使用記号）
- `app/prompts/title_description.jinja`: タイトルと紹介文を一括生成するテンプレート（Vertex 呼び出しで使用）

### ルートのタイトル・説明文のプロンプト

- **一括生成**: タイトルと説明文は `title_description.jinja` で 1 回の呼び出しのみ。JSON 壊れ時はフォールバック。
- **出力**: JSON のみ（`{"title":"...","description":"..."}`）。制約をプロンプトに書き、崩れはポストプロセスで補正。
- **禁止**: 励まし・おすすめ・感嘆符・AI主体・「〜しましょう」。**許可**: タイトルは名詞句・動詞禁止。説明文は「状況→理由→許可」・120文字以内。トーンは優しく寄り添う・無理強いしない。
- **禁止語**: `VERTEX_FORBIDDEN_WORDS` でブロック。短い／不正は `microcopy_postprocess` で補正。

## 主要な機能

### スポット検索（見どころ抽出・日本語対応）

- **二段階検索**: 第1段階で穴場キーワード検索、第2段階でテーマに合った場所タイプ（classic types）で検索。いずれも結果が空の場合はタイプ指定なしで再検索（Places API がキーワードを拒否した場合もキーワードなしで再試行）
- **サンプル点**: ルート上の 25% / 50% / 75% 地点をサンプル点とする。検索に使う点数は `PLACES_SAMPLE_POINTS_MAX` で上限（デフォルト1）。各点から `PLACES_RADIUS_M`（300m）以内を検索、1点あたり最大 `PLACES_MAX_RESULTS`（2件）まで取得
- **重複排除**: 候補の一意性は `place_id` 優先、なければ `name`、なければ `latlng` で判定
- **タイプ多様性**: 集めた候補から「タイプが被らないものを優先して選択」し、まだ余裕があれば同タイプも追加して最大5件にする（`_select_unique_types`）
- **ルート近傍フィルタ**: ルートからの距離が `SPOT_MAX_DISTANCE_M`（30m）以内のスポットのみ採用。**3件未満**のときは距離を緩和（60m → 120m）して再フィルタし、緩和時はタイプ多様化前の候補リストを再評価して最大5件を確保
- **ブロックリスト**: 名前（`PLACES_NAME_BLOCKLIST`）・タイプ（`PLACES_TYPE_BLOCKLIST`）でコンビニ・ファストフード等を除外
- **出力**: 最大5件、緯度経度つき。`name` と `type` は日本語（Places API の `languageCode: "ja"` と、英語タイプの日本語変換）

フォールバック機能の詳細は、[フォールバック機能](#フォールバック機能) を参照してください。

## ローカル開発・テスト

### ローカル開発

```bash
# 依存関係のインストール
pip install -r requirements.txt

# 環境変数の設定
export MAPS_API_KEY="your-api-key"
export VERTEX_PROJECT="your-project-id"
export VERTEX_LOCATION="us-central1"
export RANKER_URL="http://localhost:8080"

# サーバー起動
uvicorn app.main:app --reload --port 8000
```

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



## API仕様

### エンドポイント

#### `POST /route/generate`

ルート生成リクエスト

**注意:**
- `round_trip: true` の場合は `end_location` を無視します（送信は可）
- `round_trip: false` の場合は `end_location` が必須です
- 片道で直線距離が短い場合は、目標距離に合わせて回り道します

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
- `route.nav_waypoints`: ナビ用の代表点（polyline由来のみ、最大10点、周回時は始終点一致）
- `route.spots`: 見どころスポットのリスト（日本語、緯度経度つき）
  - `name`: スポット名（日本語）
  - `type`: スポットタイプ（日本語、例: "公園", "カフェ"）
  - `lat`: 緯度
  - `lng`: 経度
- `meta.fallback_used`: フォールバックが使用されたかどうか
- `meta.tools_used`: 使用したツールのリスト
- `meta.fallback_reason`: フォールバック理由コードの文字列（カンマ区切り）
- `meta.fallback_details`: フォールバック理由の詳細リスト（UI表示用）。各要素は `reason`（コード）, `description`（説明）, `impact`（影響）
- `meta.route_quality`: ルート品質情報

**生成キャッシュ:**  
同一条件（緯度・経度・距離などを丸めたキー）で TTL 内であれば、前回のレスポンスをキャッシュから返します。`debug: true` のときはキャッシュを使わず毎回生成します。同一キーへの並行リクエストは 1 本に集約し、2 本目以降は 1 本目の完了を待ってキャッシュを参照します（スタンピード防止）。環境変数は [環境変数](#環境変数) の `GENERATE_CACHE_*` を参照。

**リクエストの `debug`:**  
`debug: true` にすると、キャッシュをバイパスして毎回生成し、レスポンスの `meta` に `plan`（処理ステップ一覧）・`retry_policy`・`debug`（内部状態）などのデバッグ情報が含まれます。障害調査時に利用してください。

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

#### `GET /route/graph`

ルート生成フローの状態遷移を Mermaid 図で返します（デバッグ・ドキュメント用）。LangGraph のグラフ定義に基づきます。

**レスポンス:** テキスト（Mermaid 形式）

### フォールバック機能

以下のいずれかに該当した場合、簡易ルートやテンプレート文で応答を返します（いずれも `meta.fallback_used` / `meta.fallback_reason` / `meta.fallback_details` に記録）。

| 理由コード | 発生条件 | 動作 |
|-----------|----------|------|
| **maps_routes_failed** | Maps Routes API が失敗・タイムアウト | 開始〜終了（または開始付近）のダミーポリラインを生成し、距離は目標値に合わせる |
| **ranker_failed** | Ranker API が失敗・タイムアウト | 全候補をヒューリスティック（距離乖離等）でスコア付けし、その中から最良の1本を選択（「最初の1本」ではない） |
| **vertex_llm_failed** | Vertex AI で紹介文・タイトルの生成に失敗 | テンプレートベースの紹介文・タイトルを使用。ルートとスポットはそのまま |
| **invalid_route_detected** | 選択されたルートが無効（距離が極小、または polyline が空/不正） | そのルートを破棄し、開始〜終了のダミーポリラインに差し替え |

- 複数が同時に発生した場合、`fallback_reason` はカンマ区切りで並び、`fallback_details` に各理由の `reason` / `description` / `impact` が入ります（UIでの説明表示用）。

## 環境変数

### 必須環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `MAPS_API_KEY` | Google Maps Platform API Key（Routes API / Places API共通） | `AIza...` |
| `VERTEX_PROJECT` | Google Cloud Project ID（Vertex AI使用時） | `firstdown-482704` |
| `VERTEX_LOCATION` | Vertex AI リージョン（gemini-2.5-flash-lite 安定動作のため us-central1 推奨） | `us-central1` |

### オプション環境変数

| 変数名 | デフォルト値 | 説明 |
|--------|------------|------|
| `RANKER_URL` | `http://ranker:8080` | Ranker APIの内部URL |
| `REQUEST_TIMEOUT_SEC` | `10.0` | 外部API呼び出しのタイムアウト（秒） |
| `RANKER_TIMEOUT_SEC` | `10.0` | Ranker API呼び出しのタイムアウト（秒） |
| `VERTEX_TEXT_MODEL` | `gemini-2.5-flash-lite` | Vertex AIで使用するモデル名 |
| `VERTEX_TEMPERATURE` | `0.3` | Vertex AIの温度パラメータ |
| `VERTEX_MAX_OUTPUT_TOKENS` | `256` | Vertex AIの最大出力トークン数 |
| `VERTEX_TOP_P` | `0.95` | Vertex AIのtop_pパラメータ |
| `VERTEX_TOP_K` | `40` | Vertex AIのtop_kパラメータ |
| `VERTEX_FORBIDDEN_WORDS` | `""` | 禁止ワード（カンマ区切り） |
| `PLACES_RADIUS_M` | `300` | Places APIの検索半径（m） |
| `PLACES_MAX_RESULTS` | `2` | 1地点あたりの最大件数 |
| `PLACES_SAMPLE_POINTS_MAX` | `1` | 検索地点数（サンプル点の上限） |
| `MAX_ROUTES` | `5` | 逐次的生成で作る候補の最大本数 |
| `MIN_ROUTES` | `2` | 早期終了の下限（この本数に達し、かつ閾値超えで打ち切り） |
| `SCORE_THRESHOLD` | `0.6` | ヒューリスティックスコアの早期終了閾値（暫定）。この値以上かつ MIN_ROUTES 以上で生成を打ち切る |
| `ROUTE_DISTANCE_ERROR_RATIO_MAX` | `0.3` | 目標距離との許容誤差比率。実距離が `|実距離−目標|/目標` を超える候補は除外。短距離（≤ SHORT_DISTANCE_MAX_KM）時は 0.2 に厳格化 |
| `ROUTE_DISTANCE_RETRY_MAX` | `1` | 距離フィルタで候補が0件だった場合の再試行回数。最大試行回数はこの値+1（デフォルト2回） |
| `SHORT_DISTANCE_MAX_KM` | `3.0` | 短距離とみなす上限（km）。この値以下で誤差比率を厳格化・事前補正の対象にする |
| `SHORT_DISTANCE_TARGET_RATIO` | `0.7` | 短距離時の事前目標補正。目標距離を (目標 × この比率) に下げて Routes API に渡す（0.5〜1.0）。再試行時は観測した最良距離に合わせて目標を再計算し直す |
| `CONCURRENCY` | `2` | 外部APIの同時実行数 |
| `BQ_DATASET` | `firstdown_mvp` | BigQueryデータセット名 |
| `BQ_TABLE_REQUEST` | `route_request` | BigQueryリクエストテーブル名 |
| `BQ_TABLE_CANDIDATE` | `route_candidate` | BigQuery候補テーブル名 |
| `BQ_TABLE_PROPOSAL` | `route_proposal` | BigQuery提案テーブル名 |
| `BQ_TABLE_FEEDBACK` | `route_feedback` | BigQueryフィードバックテーブル名 |
| `FEATURES_VERSION` | `mvp_v1` | 特徴量バージョン |
| `RANKER_VERSION` | `rule_v1` | Rankerバージョン |
| `SPOT_MAX_DISTANCE_M` | `30.0` | ルートからの最大距離（m）。この距離以内のスポットを採用 |
| `SPOT_MAX_DISTANCE_M_RELAXED` | `60.0` | 緩和時の最大距離（m）。30mで3件未満のときに使用 |
| `SPOT_MAX_DISTANCE_M_FALLBACK` | `120.0` | 追加緩和時の最大距離（m）。60mでも3件未満のときに使用 |
| `PLACES_NAME_BLOCKLIST` | （コンビニ・ファストフード等） | スポット名で除外する文字列（カンマ区切り）。詳細は settings.py 参照 |
| `PLACES_TYPE_BLOCKLIST` | `convenience_store,fast_food_restaurant` | スポットタイプで除外する Places API のタイプ（カンマ区切り） |
| `LOG_LEVEL` | `INFO` | ログレベル（`DEBUG` / `INFO` / `WARNING` 等） |
| `GENERATE_CACHE_ENABLED` | `True` | `/route/generate` のインプロセス TTL キャッシュを有効にするか |
| `GENERATE_CACHE_TTL_SEC` | `120.0` | キャッシュの TTL（秒） |
| `GENERATE_CACHE_MAXSIZE` | `256` | キャッシュの最大エントリ数 |
| `GENERATE_CACHE_ROUND_LATLNG_DECIMALS` | `5` | キャッシュキー用の緯度・経度の丸め桁数 |
| `GENERATE_CACHE_ROUND_DISTANCE_DECIMALS` | `1` | キャッシュキー用の距離（km）の丸め桁数 |

### SCORE_THRESHOLD の決め方（暫定）

既存の BigQuery ログから「1リクエスト内の最高 rule_score」を抽出して分布を見る。
`rank_result` テーブルに `rule_score` が保存されている前提です。

```sql
-- 1リクエスト内の最高 rule_score 分布
WITH top_scores AS (
  SELECT
    request_id,
    MAX(rule_score) AS best_rule_score
  FROM `firstdown_mvp.rank_result`
  WHERE rule_score IS NOT NULL
  GROUP BY request_id
)
SELECT
  APPROX_QUANTILES(best_rule_score, 20) AS best_score_quantiles,
  AVG(best_rule_score) AS avg_best_score
FROM top_scores;
```

上記の分布を見て `SCORE_THRESHOLD` を仮決定し、早期終了の命中率と品質を観察しながら調整する。

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
- デフォルト: `gemini-2.5-flash-lite`
- 温度パラメータ: `0.3`
- 最大出力トークン: `256`

## 外部連携

Ranker は Cloud Run で認証必須にしている場合、呼び出し時に **OIDC ID トークン**が必要です。Agent は `app/services/id_token.py` で `audience=RANKER_URL` の ID トークンを取得し、`ranker_client.py` が `Authorization: Bearer <token>` で Ranker を呼び出します。トークンは TTL キャッシュ（55 分）で再利用します。IAM（run.invoker の付与）は [infra/README.md](../../infra/README.md#認証oidc-と-runinvoker) を参照してください。

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

### OpenTelemetry（分散トレーシング）とログ連携

- Agent は OpenTelemetry で計装され、トレースを **Google Cloud Trace** にエクスポートします（FastAPI / httpx の自動計装に加え、graph 内の主要ステップで手動スパンを付与）。詳細は [プロジェクト全体のREADME 観測可能性](../../README.md#観測可能性observability) を参照してください。
- ルート生成完了時には `message: "route_generate_summary"` の JSON ログに **trace_id**（32桁 hex）を含めています。ログで `jsonPayload.trace_id="..."` を検索し、Trace Explorer で同じ `trace_id` を指定すると、該当リクエストのトレースを確認できます。
- 起動時にはトレーシング有効時に `message: "otel_enabled"`、失敗時に `message: "otel_init_failed"` を出力します。オプションの環境変数: `OTEL_TRACES_SAMPLER_ARG`（サンプリング率、デフォルト 0.1）、`K_REVISION` / `ENV`（Resource 用）。Cloud Trace へのエクスポートには、実行用サービスアカウントに `roles/cloudtrace.agent` が必要です。

### BigQuery テーブル定義と用途

**データセット:** `firstdown_mvp`（`BQ_DATASET` で変更可能）

| テーブル / ビュー | 書き込み元 | 用途・主なカラム |
|------------------|------------|------------------|
| **route_request** | Agent API（`log_request_bq`） | リクエストごと1行。`request_id`, `theme`, `distance_km_target`, `start_lat/lng`, `round_trip`, `debug` など。ルート生成の入口ログ。 |
| **route_candidate** | Agent API（`store_candidates_bq`） | 1リクエストあたり複数行（候補数分）。`request_id`, `route_id`, `chosen_flag`, `shown_rank`, 特徴量（`distance_km`, `distance_error_ratio`, `loop_closure_m`, `poi_density` 等）。ランキング結果・採用候補の記録。 |
| **route_proposal** | Agent API（`store_proposal_bq`） | 1リクエスト1行。採用ルート `chosen_route_id`, `fallback_used`, `fallback_reason`, `tools_used`, `summary_type`, `total_latency_ms`。提案結果の要約。 |
| **route_feedback** | Agent API（`POST /route/feedback`） | ユーザー評価1件1行。`request_id`, `route_id`, `rating`, `note`。ランカー学習の正解ラベル元。 |
| **rank_result** | Ranker API | 1リクエストあたり候補数分。`request_id`, `route_id`, `rule_score`, `model_score`, `model_latency_ms`, `rule_version`, `model_version`。シャドウ推論・A/B比較用。DDL は `ml/ranker/bq/rank_result_shadow.sql`。 |
| **route_proposal_polyline** | （未使用） | 採用ルートの polyline 保存用。DDL のみ `ml/agent/bq/route_proposal_polyline.sql`。必要に応じて別ジョブで投入可能。 |

**ビュー**

| 名前 | 定義ファイル | 用途 |
|------|--------------|------|
| **training_view** | `ml/agent/bq/training_view.sql` | `route_candidate` と `route_feedback` を `request_id` + `route_id` で結合。高評価（rating 4–5）を正例、同リクエスト内の非採用候補の一部を弱い負例として `label` / `label_type` / `label_weight` を付与。Ranker の学習入力（`SELECT * FROM training_view`）。`chosen_flag` / `shown_rank` はビューから除外しリーク防止。 |

**運用・学習開始の目安**

- `ml/agent/bq/training_gate.sql`: `route_feedback` 件数と `training_view` のラベル付き件数を集計し、`feedback_count >= 1000` かつ `labeled_count >= 1000` で `training_ready` を判定。学習を開始してよいかどうかのゲート用。

**DDL の実行例**

```bash
# データセット名を変える場合は SQL 内の firstdown_mvp を編集
bq query --use_legacy_sql=false < ml/agent/bq/route_request.sql
bq query --use_legacy_sql=false < ml/agent/bq/route_candidate.sql
bq query --use_legacy_sql=false < ml/agent/bq/route_proposal.sql
bq query --use_legacy_sql=false < ml/agent/bq/route_feedback.sql
bq query --use_legacy_sql=false < ml/agent/bq/training_view.sql
# Ranker 用
bq query --use_legacy_sql=false < ml/ranker/bq/rank_result_shadow.sql
```

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

ルート生成は **LangGraph**（`app/graph.py`）でオーケストレーションされています。各ステップがノードとして定義され、状態に応じて分岐・フォールバックします。

```
ml/agent/
├── app/
│   ├── main.py              # FastAPIアプリケーション、エンドポイント定義
│   ├── graph.py             # ルート生成オーケストレーション（LangGraph）
│   ├── schemas.py           # データスキーマ（Pydantic）
│   ├── settings.py          # 設定管理
│   ├── utils.py             # ユーティリティ（例: スポットタイプの日本語化）
│   ├── prompts/             # Vertex AI用Jinjaテンプレート
│   │   ├── description.jinja
│   │   ├── title.jinja
│   │   └── title_description.jinja
│   └── services/
│       ├── maps_routes_client.py  # Maps Routes APIクライアント
│       ├── places_client.py       # Places APIクライアント（日本語対応）
│       ├── ranker_client.py       # Ranker APIクライアント
│       ├── vertex_llm.py          # Vertex AIクライアント
│       ├── feature_calc.py        # 特徴量計算
│       ├── fallback.py            # フォールバック処理
│       ├── polyline.py            # Polyline処理
│       ├── bq_writer.py           # BigQuery書き込み
│       ├── http_client.py         # 共通HTTPクライアント
│       └── __init__.py
├── bq/                       # BigQuery用SQL定義
├── Dockerfile
├── requirements.txt
├── README.md
└── test_generate_api.sh     # APIテストスクリプト
```



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

**原因**（`meta.fallback_reason` / `meta.fallback_details` の理由コード）:
- `maps_routes_failed`: Maps Routes API の失敗
- `ranker_failed`: Ranker API の失敗・タイムアウト
- `vertex_llm_failed`: Vertex AI の失敗（紹介文・タイトルのみテンプレートに差し替え）
- `invalid_route_detected`: 選択されたルートが無効（距離極小や polyline 不正）だったためダミーに差し替え

**確認方法**:
- レスポンスの `meta.fallback_reason` および `meta.fallback_details` で理由を確認
- ログで `fallback_reason` を検索
- 各サービスのヘルスチェックを実行

#### 5. デバッグモード

**用途:** ルート生成の内部状態やフォールバック理由を確認したいとき

**方法:** リクエストで `debug: true` を指定する。キャッシュをバイパスして毎回生成され、レスポンスの `meta.plan`（処理ステップ一覧）・`meta.retry_policy`・`meta.debug`（内部状態）が返る。

## リンク

- [インフラ（IaC）README](../../infra/README.md)
- [ML Services README](../README.md)
- [Ranker API README](../ranker/README.md)
- [プロジェクト全体のREADME](../../README.md)
