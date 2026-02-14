resource "google_artifact_registry_repository" "repos" {
  for_each   = toset(var.artifact_registry_repos)
  location   = var.region
  repository_id = each.value
  format     = "DOCKER"
  description = "Docker images for ${each.value}"
  depends_on = [google_project_service.apis]
}
