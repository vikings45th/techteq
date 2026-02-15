# ML Services

`ml/` には、ルート生成を担う **Agent API** とルート評価を担う **Ranker API**、および Vertex AI カスタム推論用の **predictor** が含まれます。

各サービスの API 仕様・環境変数・テスト・デプロイ・トラブルシューティングは、配下の README に記載しています。この README では、ML レイヤー全体の構成と、Agent・Ranker で共有する BigQuery まわりに絞って説明します。

## 構成

| サービス | 役割 | 詳細 |
|----------|------|------|
| **Agent** (`agent/`) | ルート生成のオーケストレーション。Maps Routes / Places / Ranker / Vertex AI / BigQuery を利用 | [agent/README.md](./agent/README.md) |
| **Ranker** (`ranker/`) | ルート候補のスコアリング。Vertex AI Endpoint またはローカル推論 | [ranker/README.md](./ranker/README.md) |
| **Vertex predictor** (`vertex/predictor/`) | Ranker 用の Vertex AI カスタム推論コンテナ。Ranker を Vertex 経由でデプロイする場合に使用 | ranker/README の「Vertex AI デプロイ」を参照 |

## Agent と Ranker の関係

```
Agent API が 1 リクエストを処理する際:
  ルート候補の逐次的生成 → 特徴量計算 → Ranker API でスコアリング → 最良ルート選択
  → スポット検索・紹介文生成 → レスポンス返却
```

処理フローの詳細・ルート候補生成の閾値・フォールバックなどは [agent/README.md](./agent/README.md) を参照してください。

## BigQuery テーブル定義と用途（ML 共通）

Agent と Ranker は同じデータセット `firstdown_mvp` を共有します。ログ・分析・ランカー学習に利用します。

| テーブル / ビュー | 書き込み元 | 用途 |
|------------------|------------|------|
| **route_request** | Agent | リクエスト 1 件 1 行 |
| **route_candidate** | Agent | 候補ルートごと 1 行（特徴量・採用フラグ等）。ランカー学習の入力元 |
| **route_proposal** | Agent | 提案 1 件 1 行（採用ルート、フォールバック理由等） |
| **route_feedback** | Agent（`POST /route/feedback`） | ユーザー評価。ランカー学習のラベル元 |
| **rank_result** | Ranker | 候補ごとの rule_score / model_score。シャドウ推論・分析用 |
| **training_view**（ビュー） | — | `route_candidate` と `route_feedback` を結合した学習用ビュー。Ranker 学習で利用 |

DDL・ビュー定義の配置、カラム説明、`training_gate`、実行例は [agent/README.md の BigQuery セクション](./agent/README.md#bigquery-テーブル定義と用途) および [ranker/README.md](./ranker/README.md)（rank_result）を参照してください。

## 学習パイプライン

Ranker のモデル学習は `ml/ranker/training/` で行います。入力は BigQuery の `training_view`（Agent が書き込む `route_candidate` と `route_feedback` を結合したビュー）です。学習手順・特徴量・Vertex へのデプロイは [ranker/README.md](./ranker/README.md) を参照してください。

## ドキュメントの役割分担

| 知りたいこと | 参照先 |
|--------------|--------|
| Agent の API 仕様、環境変数、処理フロー、ログ、デプロイ、スポット検索・フォールバック、トラブルシューティング | [agent/README.md](./agent/README.md) |
| Ranker の API 仕様、環境変数、スコアリング、学習・モデル配置、デプロイ、トラブルシューティング | [ranker/README.md](./ranker/README.md) |
| BigQuery のカラム詳細・DDL 実行・training_gate | [agent/README.md](./agent/README.md#bigquery-テーブル定義と用途) |
| インフラ・Cloud Run デプロイ・認証 | [infra/README.md](../infra/README.md) |

## リンク

- [Agent API README](./agent/README.md)
- [Ranker API README](./ranker/README.md)
- [インフラ（IaC）README](../infra/README.md)
- [プロジェクト全体の README](../README.md)
