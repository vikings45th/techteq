output "project_id" {
  value       = var.project_id
  description = "GCP プロジェクト ID"
}

output "region" {
  value       = var.region
  description = "利用リージョン"
}

output "artifact_registry_repos" {
  value       = [for r in google_artifact_registry_repository.repos : r.name]
  description = "作成した Artifact Registry リポジトリ名"
}

output "bigquery_dataset_id" {
  value       = google_bigquery_dataset.main.dataset_id
  description = "BigQuery データセット ID"
}

output "agent_runtime_sa_email" {
  value       = local.agent_runtime_sa_email
  description = "Agent Cloud Run 用サービスアカウントのメール"
}

# Terraform で Cloud Run を作成している場合のみ出力
output "agent_service_url" {
  value       = length(google_cloud_run_v2_service.agent) > 0 ? google_cloud_run_v2_service.agent[0].uri : null
  description = "Agent Cloud Run の URL（Terraform でサービスを作成している場合）"
}

output "ranker_service_url" {
  value       = length(google_cloud_run_v2_service.ranker) > 0 ? google_cloud_run_v2_service.ranker[0].uri : null
  description = "Ranker Cloud Run の URL（Terraform でサービスを作成している場合）"
}
