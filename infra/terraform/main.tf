terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 利用する API の一括有効化
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "aiplatform.googleapis.com",
    "maps-backend.googleapis.com", # Routes API 等
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
