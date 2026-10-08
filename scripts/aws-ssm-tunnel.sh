#!/usr/bin/env bash
set -euo pipefail
: "${LYNK_INSTANCE_ID:?Set the deployment instance ID}"
exec docker run --rm --interactive --network host \
  -v "$HOME/.aws:/root/.aws:ro" \
  -v /tmp/lynk-ssm-plugin/usr/local/sessionmanagerplugin/bin/session-manager-plugin:/usr/local/bin/session-manager-plugin:ro \
  public.ecr.aws/aws-cli/aws-cli@sha256:3dacc5db57c923c4223e949795f538ecf1f2212b2b7d5a028b47b97f91564c0d \
  --profile "${LYNK_AWS_PROFILE:-ngqkhai-dev}" --region "${LYNK_AWS_REGION:-ap-southeast-1}" \
  ssm start-session --target "$LYNK_INSTANCE_ID" --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["22"],"localPortNumber":["2222"]}'
