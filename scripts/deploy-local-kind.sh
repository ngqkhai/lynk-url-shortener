#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

for dependency in docker kind kubectl helm openssl curl; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    echo "Missing required command: $dependency" >&2
    exit 1
  fi
done

if ! docker info >/dev/null 2>&1; then
  echo 'Docker is not accessible. Start Docker and grant this shell access to its socket.' >&2
  exit 1
fi

if ! kind get clusters | grep -Fxq lynk-cluster; then
  bash scripts/setup-kind-cluster.sh
elif [[ "$(docker inspect --format '{{.State.Running}}' lynk-cluster-control-plane)" != true ]]; then
  docker start lynk-cluster-control-plane >/dev/null
fi

kubectl config use-context kind-lynk-cluster >/dev/null
for attempt in {1..36}; do
  if kubectl get node/lynk-cluster-control-plane --request-timeout=5s >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 36 ]]; then
    echo 'The kind API did not become available within three minutes.' >&2
    exit 1
  fi
  sleep 5
done
kubectl wait --for=condition=Ready node/lynk-cluster-control-plane --timeout=180s

if ! kubectl -n traefik get daemonset traefik >/dev/null 2>&1; then
  bash scripts/setup-kind-cluster.sh
fi

kubectl -n traefik rollout status daemonset/traefik --timeout=180s
kubectl create namespace lynk-local --dry-run=client -o yaml | kubectl apply -f -

ensure_database_secret() {
  local secret_name="$1"
  local database_name="$2"
  local service_name="$3"
  local volume_name="$4"

  if kubectl -n lynk-local get secret "$secret_name" >/dev/null 2>&1; then
    echo "Reusing Secret $secret_name."
    return
  fi
  if kubectl -n lynk-local get pvc "$volume_name" >/dev/null 2>&1; then
    echo "Secret $secret_name is missing but PVC $volume_name exists. Recover the original password before continuing." >&2
    exit 1
  fi

  local database_password
  database_password="$(openssl rand -hex 24)"
  kubectl -n lynk-local create secret generic "$secret_name" \
    --from-literal="POSTGRES_PASSWORD=$database_password" \
    --from-literal="DATABASE_URL=postgres://lynk:$database_password@$service_name:5432/$database_name" >/dev/null
  echo "Created Secret $secret_name."
}

ensure_database_secret url-service-db lynk_urls url-postgres data-url-postgres-0
ensure_database_secret redirect-service-db lynk_redirects redirect-postgres data-redirect-postgres-0

if ! kubectl -n lynk-local get secret lynk-redis-auth >/dev/null 2>&1; then
  redis_password="$(openssl rand -hex 24)"
  kubectl -n lynk-local create secret generic lynk-redis-auth \
    --from-literal="redis-password=$redis_password" >/dev/null
  echo 'Created Secret lynk-redis-auth.'
fi

kubectl -n lynk-local apply -f infra/k8s/local/
kubectl -n lynk-local rollout status statefulset/url-postgres --timeout=240s
kubectl -n lynk-local rollout status statefulset/redirect-postgres --timeout=240s
kubectl -n lynk-local rollout status deployment/lynk-redis --timeout=240s

image_tag="local-$(date -u +%Y%m%d%H%M%S)-$$"
docker build -t "lynk-url-service:$image_tag" -f services/url-service/Dockerfile .
docker build -t "lynk-redirect-service:$image_tag" -f services/redirect-service/Dockerfile .
kind load docker-image "lynk-url-service:$image_tag" "lynk-redirect-service:$image_tag" --name lynk-cluster

helm upgrade --install lynk-services infra/k8s/helm/lynk-services \
  --namespace lynk-local \
  --values infra/k8s/helm/lynk-services/values-local.yaml \
  --set-string "global.imageTag=$image_tag" \
  --wait --timeout=5m

kubectl -n lynk-local rollout status deployment/url-service --timeout=180s
kubectl -n lynk-local rollout status deployment/redirect-service --timeout=180s

base_url='http://lynk.localhost'
resolve='lynk.localhost:80:127.0.0.1'
curl --fail --silent --show-error --max-time 10 --resolve "$resolve" "$base_url/health/ready" >/dev/null

short_code="Local$(date -u +%s)"
create_status="$(curl --silent --show-error --max-time 10 --resolve "$resolve" \
  --output /dev/null --write-out '%{http_code}' \
  --header 'content-type: application/json' \
  --data "{\"originalUrl\":\"https://example.com\",\"customAlias\":\"$short_code\"}" \
  "$base_url/api/v1/urls")"
if [[ "$create_status" != 201 ]]; then
  echo "Smoke test failed: URL creation returned HTTP $create_status." >&2
  exit 1
fi

redirect_result="$(curl --silent --show-error --max-time 10 --resolve "$resolve" \
  --output /dev/null --write-out '%{http_code} %{redirect_url}' \
  "$base_url/$short_code")"
if [[ "$redirect_result" != '302 https://example.com/' && "$redirect_result" != '302 https://example.com' ]]; then
  echo "Smoke test failed: redirect returned $redirect_result." >&2
  exit 1
fi

echo "Local deployment ready: $base_url/$short_code -> https://example.com"
echo 'Data remains on the PostgreSQL PVCs while the kind cluster exists.'
