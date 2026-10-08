#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
cd /opt/lynk/source
kubectl create namespace lynk-aws --dry-run=client -o yaml | kubectl apply -f -
for service in url redirect auth; do
  kubectl -n lynk-aws create secret generic "$service-service-db" --from-env-file="/opt/lynk/secrets/$service.env" --dry-run=client -o yaml | kubectl apply -f -
done
kubectl -n lynk-aws create secret generic lynk-redis-auth --from-file=redis-password=/opt/lynk/secrets/redis-password --dry-run=client -o yaml | kubectl apply -f -
kubectl -n lynk-aws create secret generic lynk-jwt-keys --from-file=/opt/lynk/secrets/jwt-private.pem --from-file=/opt/lynk/secrets/jwt-public.pem --dry-run=client -o yaml | kubectl apply -f -
kubectl -n lynk-aws create secret generic lynk-gateway-ca --from-file=ca.crt=/opt/lynk/secrets/ca.crt --dry-run=client -o yaml | kubectl apply -f -
kubectl -n lynk-aws create secret generic lynk-gateway-server --from-file=ca.crt=/opt/lynk/secrets/ca.crt --from-file=server.crt=/opt/lynk/secrets/server.crt --from-file=server.key=/opt/lynk/secrets/server.key --dry-run=client -o yaml | kubectl apply -f -
kubectl -n lynk-aws create secret tls lynk-gateway-client --cert=/opt/lynk/secrets/client.crt --key=/opt/lynk/secrets/client.key --dry-run=client -o yaml | kubectl apply -f -
helm repo add traefik https://traefik.github.io/charts
helm repo update traefik
desired=$(sha256sum infra/aws/traefik-values.yaml | cut -d' ' -f1)
current=$(cat /opt/lynk/traefik-values.sha256 2>/dev/null || true)
if [[ "$desired" != "$current" ]] || ! helm status traefik -n traefik >/dev/null 2>&1; then
  helm upgrade --install traefik traefik/traefik --version 41.5.0 -n traefik --create-namespace -f infra/aws/traefik-values.yaml --wait --timeout 5m
  printf '%s' "$desired" > /opt/lynk/traefik-values.sha256
fi
kubectl -n lynk-aws apply -f infra/aws/redis.yaml -f infra/aws/kafka.yaml
kubectl -n lynk-aws rollout status statefulset/kafka --timeout=300s
if ! kubectl -n lynk-aws get job kafka-topics >/dev/null 2>&1; then
  kubectl -n lynk-aws apply -f infra/k8s/local/kafka-topics.yaml
fi
kubectl -n lynk-aws wait --for=condition=complete job/kafka-topics --timeout=180s
