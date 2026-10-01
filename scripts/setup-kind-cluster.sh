#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# setup-kind-cluster.sh
# Bootstrap the local lynk-cluster with Traefik.
# Usage: bash scripts/setup-kind-cluster.sh
# ─────────────────────────────────────────────────────────────────────────────

# Check prerequisites
command -v kind  >/dev/null 2>&1 || { echo "ERROR: kind not found. Run: curl -Lo ~/.local/bin/kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64 && chmod +x ~/.local/bin/kind"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "ERROR: kubectl not found."; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "ERROR: helm not found."; exit 1; }

echo ""
echo "════════════════════════════════════════════"
echo "  🚀 Lynk Cluster Bootstrap"
echo "════════════════════════════════════════════"
echo ""

# ── 1. Create kind cluster ────────────────────────────────────────────────────
if kind get clusters | grep -Fxq "lynk-cluster"; then
  echo "ℹ️  Cluster 'lynk-cluster' already exists. Skipping creation."
else
  echo "📦 Creating kind cluster 'lynk-cluster'..."
  kind create cluster --config infra/k8s/kind-config.yaml
fi

kubectl config use-context kind-lynk-cluster
echo "✅ Cluster ready."

# ── 2. Install Traefik Ingress Controller ────────────────────────────────────
echo ""
echo "🔀 Installing Traefik Ingress Controller..."
traefik_chart_version=41.5.0
helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
helm repo update traefik

if helm status traefik --namespace traefik > /dev/null 2>&1; then
  echo "ℹ️  Traefik already installed. Upgrading..."
  helm upgrade traefik traefik/traefik \
    --version "$traefik_chart_version" \
    --namespace traefik \
    --values infra/k8s/traefik-values.yaml \
    --wait --timeout=120s
else
  helm install traefik traefik/traefik \
    --version "$traefik_chart_version" \
    --namespace traefik \
    --create-namespace \
    --values infra/k8s/traefik-values.yaml \
    --wait --timeout=120s
fi
echo "✅ Traefik installed."

# ── 3. Print access information ──────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  ✅ Bootstrap Complete!"
echo "════════════════════════════════════════════"
echo ""
echo "  Local Ingress → http://lynk.localhost (port 80)"
echo ""
