#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${LYNK_KEY_DIR:?Set the directory printed by LYNK_KEEP_STACK=true make test-sprint3a}"
project="${LYNK_COMPOSE_PROJECT:-lynk-3a-test}"
results_dir="${LYNK_RESULTS_DIR:-/tmp/lynk-3a-benchmark}"
mkdir -p "$results_dir"
results_dir="$(realpath "$results_dir")"
docker run --rm --network "${project}_default" --user 0 \
  -e SSL_CERT_FILE=/tls/ca.crt \
  -v "$PWD/benchmarks/k6-phantom.js:/scripts/phantom.js:ro" \
  -v "$LYNK_KEY_DIR/client.crt:/tls/client.crt:ro" \
  -v "$LYNK_KEY_DIR/client.key:/tls/client.key:ro" \
  -v "$LYNK_KEY_DIR/ca.crt:/tls/ca.crt:ro" \
  -v "$results_dir:/results" \
  grafana/k6:1.0.0 run /scripts/phantom.js
