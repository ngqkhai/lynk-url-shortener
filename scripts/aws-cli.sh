#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker run --rm -v "$HOME/.aws:/root/.aws:ro" -v "$PWD:/workspace:ro" -v /tmp/lynk-aws-payloads:/payloads:ro \
  public.ecr.aws/aws-cli/aws-cli@sha256:3dacc5db57c923c4223e949795f538ecf1f2212b2b7d5a028b47b97f91564c0d \
  --profile "${LYNK_AWS_PROFILE:-ngqkhai-dev}" --region "${LYNK_AWS_REGION:-ap-southeast-1}" "$@"
