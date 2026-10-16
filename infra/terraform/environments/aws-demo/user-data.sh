#!/bin/bash
set -euo pipefail
# Wait for the Elastic IP to be attached before fetching dependencies.
for attempt in $(seq 1 120); do
  if curl -fsS --connect-timeout 3 https://get.k3s.io -o /tmp/install-k3s.sh; then break; fi
  sleep 5
done
apt-get update
apt-get install -y curl ca-certificates jq git unzip
snap start amazon-ssm-agent || true
mkdir -p /etc/rancher/k3s
cat > /etc/rancher/k3s/config.yaml <<'CONFIG'
write-kubeconfig-mode: "0600"
disable:
  - traefik
  - servicelb
secrets-encryption: true
node-label:
  - ingress-ready=true
CONFIG
INSTALL_K3S_VERSION='v1.37.1+k3s1' sh /tmp/install-k3s.sh
curl -fsS https://get.helm.sh/helm-v3.21.2-linux-amd64.tar.gz -o /tmp/helm.tar.gz
tar -xzf /tmp/helm.tar.gz -C /tmp
install /tmp/linux-amd64/helm /usr/local/bin/helm
mkdir -p /opt/lynk
chmod 700 /opt/lynk
