variable "project_id" {
  type        = string
  description = "GCP プロジェクト ID"
}

variable "region" {
  type        = string
  default     = "asia-northeast1"
  description = "メインで利用するリージョン（Cloud Run, Artifact Registry 等）"
}

variable "bq_dataset_id" {
  type        = string
  default     = "firstdown_mvp"
  description = "BigQuery データセット ID"
}

variable "bq_dataset_description" {
  type        = string
  default     = "ログ・分析用データセット"
  description = "BigQuery データセットの説明（プロジェクト名などは含めず汎用でよい）"
}

variable "artifact_registry_repos" {
  type        = list(string)
  default     = ["agent-repo", "ranker-repo"]
  description = "作成する Artifact Registry リポジトリ名のリスト"
}

variable "agent_runtime_sa_name" {
  type        = string
  default     = "agent-runtime-sa"
  description = "Agent Cloud Run 用のサービスアカウント名"
}

# true: 新規作成。false: 既存の SA を data で参照し IAM のみ付与（既に手動で SA がある場合）
variable "create_agent_runtime_sa" {
  type        = bool
  default     = true
  description = "Agent 用サービスアカウントを新規作成するか。false のときは既存 SA に IAM のみ付与"
}

# -----------------------------------------------------------------------------
# Cloud Run（実環境のパラメータを定義化。デプロイは GitHub Actions の gcloud で実施）
# サービス名・URL・キー・バージョンなど「環境ごとに変えるもの」は変数化。
# タイムアウト・メモリ・CPU・スケール・IAM ロールなどはコードに記載（テンプレートとしてそのまま利用可）。
# -----------------------------------------------------------------------------

variable "agent_service_name" {
  type        = string
  default     = "agent"
  description = "Agent Cloud Run のサービス名（他プロジェクトでテンプレート利用時に変更）"
}

variable "ranker_service_name" {
  type        = string
  default     = "ranker"
  description = "Ranker Cloud Run のサービス名（他プロジェクトでテンプレート利用時に変更）"
}

variable "agent_image" {
  type        = string
  default     = ""
  description = "Agent Cloud Run のコンテナイメージ。空のときはテンプレートとして定義のみ（apply でサービスを作る場合は CI デプロイ後のイメージ URL を渡す）"
}

variable "ranker_image" {
  type        = string
  default     = ""
  description = "Ranker Cloud Run のコンテナイメージ。空のときはテンプレートとして定義のみ"
}

# Agent の RANKER_URL。他環境では tfvars で上書きすること（Terraform で Ranker を先に作る場合は output を参照可）
variable "ranker_service_url" {
  type        = string
  default     = ""
  description = "Ranker API の URL（Agent の RANKER_URL）。未設定だと空文字になるため、Agent 利用時は tfvars または CI で設定すること"
}

# シークレットは Terraform に持たず CI で注入する想定。apply 時に渡す場合はここで指定可
variable "agent_env_maps_api_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Agent の MAPS_API_KEY。空なら Terraform では設定しない（CI の gcloud deploy で --set-env-vars に含める）"
}

# ----- アプリ側のバージョン・モデル名（環境ごとに変える場合はここだけ変更） -----
variable "agent_env_features_version" {
  type        = string
  default     = "mvp_v1"
  description = "Agent の FEATURES_VERSION"
}

variable "agent_env_vertex_text_model" {
  type        = string
  default     = "gemini-2.5-flash"
  description = "Agent の VERTEX_TEXT_MODEL"
}

variable "ranker_env_model_version" {
  type        = string
  default     = "shadow_xgb_v2"
  description = "Ranker の MODEL_VERSION"
}

variable "ranker_env_ranker_version" {
  type        = string
  default     = "rule_v1"
  description = "Ranker の RANKER_VERSION"
}
