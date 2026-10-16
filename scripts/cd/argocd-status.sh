#!/usr/bin/env bash
set -euo pipefail

values_revision=${1:?expected values revision required}
release_sha=${2:?expected release SHA required}
url_digest=${3:?expected URL image digest required}
redirect_digest=${4:?expected redirect image digest required}
auth_digest=${5:?expected auth image digest required}

for value in "$values_revision" "$release_sha"; do
  [[ "$value" =~ ^[0-9a-f]{40}$ ]] || { echo 'invalid revision argument' >&2; exit 2; }
done
for value in "$url_digest" "$redirect_digest" "$auth_digest"; do
  [[ "$value" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'invalid image digest argument' >&2; exit 2; }
done

kubectl=/usr/local/bin/kubectl
app="$($kubectl get application aws-demo -n argocd -o json)"
python3 - "$app" "$values_revision" <<'PY'
import json, sys
app = json.loads(sys.argv[1])
expected = sys.argv[2]
revisions = app.get('status', {}).get('sync', {}).get('revisions', [])
if expected not in revisions:
    raise SystemExit('Argo has not observed the expected values revision')
if app.get('status', {}).get('sync', {}).get('status') != 'Synced':
    raise SystemExit('Argo Application is not Synced')
if app.get('status', {}).get('health', {}).get('status') != 'Healthy':
    raise SystemExit('Argo Application is not Healthy')
operation = app.get('status', {}).get('operationState', {})
if operation and operation.get('phase') not in ('Succeeded',):
    raise SystemExit('latest Argo operation did not succeed')
PY

check_deployment() {
  local name=$1 digest=$2 deployment pods
  deployment="$($kubectl get deployment "$name" -n lynk-aws -o json)"
  pods="$($kubectl get pods -n lynk-aws -l "app=$name" -o json)"
  python3 - "$deployment" "$pods" "$digest" "$name" <<'PY'
import json, sys
deployment, pods = map(json.loads, sys.argv[1:3])
expected, name = sys.argv[3:5]
spec = deployment.get('spec', {})
desired_replicas = spec.get('replicas', 1)
if deployment.get('status', {}).get('readyReplicas', 0) < desired_replicas:
    raise SystemExit(f'{name} Deployment does not have all desired replicas ready')
containers = spec.get('template', {}).get('spec', {}).get('containers', [])
container = next((item for item in containers if item.get('name') == name), None)
if not container or not container.get('image', '').endswith('@' + expected):
    raise SystemExit(f'{name} Deployment does not declare the expected digest')
ready = [pod for pod in pods.get('items', []) if pod.get('status', {}).get('phase') == 'Running']
if not ready:
    raise SystemExit(f'{name} has no Running Pod')
for pod in ready:
    statuses = pod.get('status', {}).get('containerStatuses', [])
    status = next((item for item in statuses if item.get('name') == name), None)
    if not status or not status.get('ready') or not status.get('imageID', '').endswith('@' + expected):
        raise SystemExit(f'{name} Pod readiness or runtime image digest does not match')
PY
}

check_deployment url-service "$url_digest"
check_deployment redirect-service "$redirect_digest"
check_deployment auth-service "$auth_digest"
smoke="$($kubectl get job lynk-postsync-smoke -n lynk-aws -o json)"
smoke_pods="$($kubectl get pods -n lynk-aws -l app=lynk-postsync-smoke -o json)"
python3 - "$smoke" "$smoke_pods" "$url_digest" <<'PY'
import json, sys
job = json.loads(sys.argv[1])
pods = json.loads(sys.argv[2])
expected = sys.argv[3]
if job.get('status', {}).get('succeeded', 0) < 1:
    raise SystemExit('PostSync smoke Job has not succeeded')
containers = job.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
if not containers or not containers[0].get('image', '').endswith('@' + expected):
    raise SystemExit('PostSync smoke Job does not use the expected release image')
completed = [pod for pod in pods.get('items', []) if pod.get('status', {}).get('phase') == 'Succeeded']
if not any(any(status.get('name') == containers[0]['name'] and status.get('imageID', '').endswith('@' + expected)
               for status in pod.get('status', {}).get('containerStatuses', [])) for pod in completed):
    raise SystemExit('PostSync smoke Pod did not complete with the expected release image')
PY
printf '{"values_revision":"%s","release_sha":"%s","status":"Healthy","smoke":"Succeeded"}\n' "$values_revision" "$release_sha"
