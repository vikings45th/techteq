# 既存 SA を参照（create_agent_runtime_sa = false のとき）
data "google_service_account" "agent_runtime_existing" {
  count      = var.create_agent_runtime_sa ? 0 : 1
  account_id = var.agent_runtime_sa_name
  project    = var.project_id
}

# Agent Cloud Run 用サービスアカウント（新規作成時）
resource "google_service_account" "agent_runtime" {
  count        = var.create_agent_runtime_sa ? 1 : 0
  account_id   = var.agent_runtime_sa_name
  display_name = "Agent Cloud Run runtime"
  description  = "Agent API の Cloud Run で使用"
}

locals {
  agent_runtime_sa_email = var.create_agent_runtime_sa ? google_service_account.agent_runtime[0].email : data.google_service_account.agent_runtime_existing[0].email
}

# Agent が Vertex AI を呼ぶための権限
resource "google_project_iam_member" "agent_vertex" {
  for_each = toset([
    "roles/aiplatform.user",
  ])
  project = var.project_id
  role   = each.value
  member = "serviceAccount:${local.agent_runtime_sa_email}"
}

# Agent が BigQuery に書き込むための権限
resource "google_project_iam_member" "agent_bigquery" {
  for_each = toset([
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
  ])
  project = var.project_id
  role   = each.value
  member = "serviceAccount:${local.agent_runtime_sa_email}"
}