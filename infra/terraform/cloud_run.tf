# -----------------------------------------------------------------------------
# Cloud Run サービス定義（実環境のパラメータをコード化）
# デプロイは GitHub Actions の gcloud run deploy で実施。この定義は「設定の参照・テンプレート」。
# イメージを変数で渡して apply すると、Terraform でサービスを作成・更新することも可能。
# -----------------------------------------------------------------------------

locals {
  # イメージを渡したときだけ Terraform で Cloud Run を管理（空なら CI デプロイのみでこの定義はテンプレートとして参照用）
  create_agent_service  = var.agent_image != ""
  create_ranker_service = var.ranker_image != ""
}

# ---------- Agent ----------
resource "google_cloud_run_v2_service" "agent" {
  count    = local.create_agent_service ? 1 : 0
  name     = var.agent_service_name
  location = var.region
  project  = var.project_id

  template {
    timeout                         = "300s"
    max_instance_request_concurrency = 10
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    containers {
      image = var.agent_image
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = true
      }
      env {
        name  = "RANKER_URL"
        value = var.ranker_service_url
      }
      env {
        name  = "RANKER_TIMEOUT_SEC"
        value = "10"
      }
      env {
        name  = "REQUEST_TIMEOUT_SEC"
        value = "10"
      }
      env {
        name  = "BQ_DATASET"
        value = var.bq_dataset_id
      }
      env {
        name  = "FEATURES_VERSION"
        value = var.agent_env_features_version
      }
      env {
        name  = "VERTEX_PROJECT"
        value = var.project_id
      }
      env {
        name  = "VERTEX_LOCATION"
        value = var.agent_env_vertex_location
      }
      env {
        name  = "VERTEX_TEXT_MODEL"
        value = var.agent_env_vertex_text_model
      }
      dynamic "env" {
        for_each = var.agent_env_maps_api_key != "" ? [1] : []
        content {
          name  = "MAPS_API_KEY"
          value = var.agent_env_maps_api_key
        }
      }
    }
    service_account = local.agent_runtime_sa_email
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}

# Agent の呼び出し許可（認証必須）。Web の Cloud Run 用 SA など、agent_invoker_sa_email に指定した SA にのみ付与。
resource "google_cloud_run_v2_service_iam_member" "agent_invoker" {
  count    = local.create_agent_service && var.agent_invoker_sa_email != "" ? 1 : 0
  name     = google_cloud_run_v2_service.agent[0].name
  location = google_cloud_run_v2_service.agent[0].location
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.agent_invoker_sa_email}"
}

# ---------- Ranker ----------
resource "google_cloud_run_v2_service" "ranker" {
  count    = local.create_ranker_service ? 1 : 0
  name     = var.ranker_service_name
  location = var.region
  project  = var.project_id

  template {
    timeout                         = "30s"
    max_instance_request_concurrency = 10
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    containers {
      image = var.ranker_image
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }
      env {
        name  = "MODEL_VERSION"
        value = var.ranker_env_model_version
      }
      env {
        name  = "RANKER_VERSION"
        value = var.ranker_env_ranker_version
      }
      dynamic "env" {
        for_each = var.ranker_env_model_inference_mode != "" ? [1] : []
        content {
          name  = "MODEL_INFERENCE_MODE"
          value = var.ranker_env_model_inference_mode
        }
      }
      dynamic "env" {
        for_each = var.ranker_env_vertex_endpoint_id != "" ? [1] : []
        content {
          name  = "VERTEX_PROJECT"
          value = var.ranker_env_vertex_project != "" ? var.ranker_env_vertex_project : var.project_id
        }
      }
      dynamic "env" {
        for_each = var.ranker_env_vertex_endpoint_id != "" ? [1] : []
        content {
          name  = "VERTEX_LOCATION"
          value = var.ranker_env_vertex_location != "" ? var.ranker_env_vertex_location : var.region
        }
      }
      dynamic "env" {
        for_each = var.ranker_env_vertex_endpoint_id != "" ? [1] : []
        content {
          name  = "VERTEX_ENDPOINT_ID"
          value = var.ranker_env_vertex_endpoint_id
        }
      }
      dynamic "env" {
        for_each = var.ranker_env_vertex_endpoint_id != "" ? [1] : []
        content {
          name  = "VERTEX_TIMEOUT_S"
          value = var.ranker_env_vertex_timeout_s
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}

# Ranker の呼び出し許可（認証必須）。Agent の実行用 SA にのみ付与。
resource "google_cloud_run_v2_service_iam_member" "ranker_invoker_agent" {
  count    = local.create_ranker_service ? 1 : 0
  name     = google_cloud_run_v2_service.ranker[0].name
  location = google_cloud_run_v2_service.ranker[0].location
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.agent_runtime_sa_email}"
}
