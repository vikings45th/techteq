#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# 18特徴量版モデルを GCS に上げ、Vertex AI Predictor をビルドし、
# Vertex AI Model をアップロードして既存 Endpoint にデプロイするスクリプト。
# 実行前に gcloud auth login と gcloud config set project を済ませてください。
# -----------------------------------------------------------------------------
set -euo pipefail

PROJECT="${PROJECT_ID:-firstdown-482704}"
REGION="${REGION:-asia-northeast1}"
BUCKET_NAME="${BUCKET_NAME:-firstdown-vertex-models}"
VERSION="${VERSION:-shadow_xgb_18feat}"
REPO_NAME="${REPO_NAME:-vertex-predictor}"
# 既存 Endpoint にデプロイする場合は ID を指定（未設定時は新規 Endpoint 作成）
ENDPOINT_ID="${VERTEX_ENDPOINT_ID:-}"
DISPLAY_NAME_MODEL="ranker-xgb-18feat"
DISPLAY_NAME_DEPLOY="ranker-xgb-18feat"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RANKER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERTEX_PREDICTOR_DIR="$(cd "${RANKER_DIR}/../vertex/predictor" && pwd)"
MODELS_DIR="${RANKER_DIR}/models"

echo "=== 0) GCS バケットが無い場合は作成、Vertex 用 SA にオブジェクト閲覧権限付与 ==="
if ! gsutil ls "gs://${BUCKET_NAME}/" &>/dev/null; then
  gsutil mb -p "${PROJECT}" -l "${REGION}" "gs://${BUCKET_NAME}/"
fi
# Vertex AI のカスタム予測コンテナが GCS を読めるよう、デフォルト compute SA に権限付与
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT}" --format="value(projectNumber)")
gsutil iam ch "serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com:objectViewer" "gs://${BUCKET_NAME}" || true

echo "=== 1) GCS に成果物をアップロード ==="
gsutil -m cp "${MODELS_DIR}/model.xgb.json" "gs://${BUCKET_NAME}/ranker/${VERSION}/model.xgb.json"
gsutil -m cp "${MODELS_DIR}/feature_columns.json" "gs://${BUCKET_NAME}/ranker/${VERSION}/feature_columns.json"
gsutil -m cp "${MODELS_DIR}/metadata.json" "gs://${BUCKET_NAME}/ranker/${VERSION}/metadata.json"
echo "Uploaded to gs://${BUCKET_NAME}/ranker/${VERSION}/"

echo "=== 2) Predictor イメージをビルドして Artifact Registry へ push ==="
IMAGE_URI="asia-northeast1-docker.pkg.dev/${PROJECT}/${REPO_NAME}/vertex-predictor:${VERSION}"
gcloud builds submit --tag "${IMAGE_URI}" "${VERTEX_PREDICTOR_DIR}"

echo "=== 3) Vertex AI Model をアップロード ==="
gcloud ai models upload \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --display-name="${DISPLAY_NAME_MODEL}" \
  --container-image-uri="${IMAGE_URI}" \
  --container-env-vars="MODEL_GCS_URI=gs://${BUCKET_NAME}/ranker/${VERSION}/model.xgb.json,FEATURES_GCS_URI=gs://${BUCKET_NAME}/ranker/${VERSION}/feature_columns.json,METADATA_GCS_URI=gs://${BUCKET_NAME}/ranker/${VERSION}/metadata.json" \
  --container-health-route=/health \
  --container-predict-route=/predict

# アップロード直後のモデル ID を取得（一覧の先頭を利用）
MODEL_ID=$(gcloud ai models list --region="${REGION}" --project="${PROJECT}" --filter="displayName=${DISPLAY_NAME_MODEL}" --format="value(name)" --sort-by="~createTime" --limit=1)
if [[ -z "${MODEL_ID}" ]]; then
  echo "ERROR: Failed to get MODEL_ID for displayName=${DISPLAY_NAME_MODEL}"
  exit 1
fi
echo "Uploaded model: ${MODEL_ID}"

if [[ -z "${ENDPOINT_ID}" ]]; then
  echo "=== 4a) 新規 Vertex AI Endpoint を作成 ==="
  gcloud ai endpoints create \
    --region="${REGION}" \
    --project="${PROJECT}" \
    --display-name=ranker-xgb-endpoint
  ENDPOINT_ID=$(gcloud ai endpoints list --region="${REGION}" --project="${PROJECT}" --filter="displayName=ranker-xgb-endpoint" --format="value(name)" --sort-by="~createTime" --limit=1)
  echo "Created endpoint: ${ENDPOINT_ID}"
else
  echo "=== 4b) 既存 Endpoint を使用: ${ENDPOINT_ID} ==="
fi

echo "=== 5) Endpoint に Model をデプロイ ==="
# コンテナが GCS からモデルを読むため、デフォルト Compute SA を明示指定（要: 当該 SA にバケットの objectViewer 付与）
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT}" --format="value(projectNumber)")
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud ai endpoints deploy-model "${ENDPOINT_ID}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --model="${MODEL_ID}" \
  --display-name="${DISPLAY_NAME_DEPLOY}" \
  --machine-type=n1-standard-2 \
  --min-replica-count=1 \
  --max-replica-count=2 \
  --service-account="${SA_EMAIL}"

echo ""
echo "=== デプロイ完了 ==="
echo "ENDPOINT_ID (Ranker の VERTEX_ENDPOINT_ID に設定): ${ENDPOINT_ID}"
echo "MODEL_VERSION (Ranker の MODEL_VERSION に設定): ${VERSION}"
echo ""
echo "Ranker を Vertex 推論にするには以下を設定してください:"
echo "  MODEL_INFERENCE_MODE=vertex"
echo "  VERTEX_PROJECT=${PROJECT}"
echo "  VERTEX_LOCATION=${REGION}"
echo "  VERTEX_ENDPOINT_ID=${ENDPOINT_ID}"
echo "  MODEL_VERSION=${VERSION}"
