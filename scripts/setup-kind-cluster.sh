#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# setup-kind-cluster.sh
# Bootstrap the lynk-cluster with Traefik + ArgoCD in one command.
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
if kind get clusters | grep -q "lynk-cluster"; then
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
helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
helm repo update traefik

if helm status traefik --namespace traefik > /dev/null 2>&1; then
  echo "ℹ️  Traefik already installed. Upgrading..."
  helm upgrade traefik traefik/traefik \
    --namespace traefik \
    --values infra/k8s/traefik-values.yaml \
    --wait --timeout=120s
else
  helm install traefik traefik/traefik \
    --namespace traefik \
    --create-namespace \
    --values infra/k8s/traefik-values.yaml \
    --wait --timeout=120s
fi
echo "✅ Traefik installed."

# ── 3. Install ArgoCD ────────────────────────────────────────────────────────
echo ""
echo "🔄 Installing ArgoCD..."
helm repo add argo https://argoproj.github.io/argo-helm 2>/dev/null || true
helm repo update argo

if helm status argocd --namespace argocd > /dev/null 2>&1; then
  echo "ℹ️  ArgoCD already installed. Skipping."
else
  helm install argocd argo/argo-cd \
    --namespace argocd \
    --create-namespace \
    --set server.service.type=NodePort \
    --set server.service.nodePortHttp=32081 \
    --wait --timeout=180s
fi
echo "✅ ArgoCD installed."

# ── 4. Create lynk-staging namespace ──────────────────────────────────────────
kubectl create namespace lynk-staging --dry-run=client -o yaml | kubectl apply -f -

# ── 5. Print access information ──────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  ✅ Bootstrap Complete!"
echo "════════════════════════════════════════════"
echo ""
echo "  Traefik HTTP  → http://localhost:32080"
echo ""
echo "  ArgoCD UI     → http://localhost:32081"
echo "  Initial admin password:"
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" 2>/dev/null | base64 -d && echo "" || echo "  (run: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
echo ""
