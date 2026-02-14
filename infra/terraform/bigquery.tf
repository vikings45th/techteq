resource "google_bigquery_dataset" "main" {
  dataset_id   = var.bq_dataset_id
  location     = var.region
  description  = var.bq_dataset_description
  depends_on   = [google_project_service.apis]
}
