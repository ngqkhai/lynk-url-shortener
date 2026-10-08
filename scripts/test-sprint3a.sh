#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export LYNK_COMPOSE_PROJECT="${LYNK_COMPOSE_PROJECT:-lynk-3a-test}"
export LYNK_KEY_DIR="$(mktemp -d /tmp/lynk-compose-keys.XXXXXX)"
compose=(docker compose -p "$LYNK_COMPOSE_PROJECT" -f infra/docker/compose.3a.yml --profile gateway)
cleanup() {
  if [[ "${LYNK_KEEP_STACK:-false}" != true ]]; then
    "${compose[@]}" down --volumes --remove-orphans >/dev/null
    rm -rf "$LYNK_KEY_DIR"
  else
    echo "Kept stack $LYNK_COMPOSE_PROJECT; keys in $LYNK_KEY_DIR"
  fi
}
trap cleanup EXIT
bash scripts/generate-local-keys.sh "$LYNK_KEY_DIR"
# Only mounted leaf files are readable inside containers; parent stays mode 0700.
chmod 444 "$LYNK_KEY_DIR"/*.pem "$LYNK_KEY_DIR"/*.crt "$LYNK_KEY_DIR"/server.key "$LYNK_KEY_DIR"/client.key
if [[ "${LYNK_SKIP_BUILD:-false}" != true ]]; then
  for service in auth-service url-service redirect-service; do
    docker build -t "lynk-$service:sprint3a" -f "services/$service/Dockerfile" .
  done
fi
"${compose[@]}" up -d
python3 scripts/smoke-sprint3a.py
python3 scripts/test-mtls-sprint3a.py
