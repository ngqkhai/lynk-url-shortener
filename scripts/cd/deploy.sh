#!/usr/bin/env bash
# Root-only node entrypoint. No DB credentials or arbitrary commands in arguments.
set -Eeuo pipefail
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
export AWS_DEFAULT_REGION=ap-southeast-1
bucket=lynk-k3s-dev-artifactbucket-acumvnfx55sd
state="${LYNK_RELEASE_ROOT:-/opt/lynk/releases}"
mkdir -p "$state"
exec 9>"$state/deploy.lock"
flock -w "${LYNK_LOCK_WAIT_SECONDS:-1200}" 9 || { echo 'Another deployment holds the lock'; exit 1; }
action="${1:-}"
sha="${2:-}"
revision="${3:-0}"
[[ "$action" =~ ^(deploy|rollback)$ && "$sha" =~ ^[0-9a-f]{40}$ && "$revision" =~ ^[0-9]+$ ]] || exit 2
systemctl is-active --quiet k3s
kubectl wait --for=condition=Ready node --all --timeout=60s
# Reserve room for image extraction; do not resize disks automatically.
[[ $(df --output=avail -k /var/lib/rancher/k3s | tail -1) -gt 1048576 ]] || { echo 'Less than 1 GiB disk free'; exit 1; }
mkdir -p "$state/$sha"
work="$state/$sha"
aws s3 cp "s3://$bucket/releases/$sha/release.tar.gz" "$work/release.tar.gz" --only-show-errors
aws s3 cp "s3://$bucket/releases/$sha/release.sha256" "$work/release.sha256" --only-show-errors
(cd "$work" && sha256sum -c release.sha256)
# Reject traversal, links and devices before extracting a release bundle.
python3 - "$work" "$sha" <<'PY'
import json, pathlib, re, sys, tarfile
root = pathlib.Path(sys.argv[1])
with tarfile.open(root / 'release.tar.gz') as archive:
    for member in archive.getmembers():
        p = pathlib.PurePosixPath(member.name)
        if p.is_absolute() or '..' in p.parts or not (member.isfile() or member.isdir()):
            raise SystemExit('Unsafe archive member')
    archive.extractall(root / 'bundle', filter='data')
manifest = json.loads((root / 'bundle/release.json').read_text())
assert manifest['version'] == 1 and manifest['commit'] == sys.argv[2]
for service in ['url', 'redirect', 'auth']:
    image = manifest['images'][service + 'Service']['image']
    assert image['repository'] == 'ghcr.io/ngqkhai/lynk-' + service + '-service'
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', image['digest'])
PY
cd "$work/bundle"
previous=$(helm history lynk-services -n lynk-aws -o json | python3 -c 'import json,sys; r=[x for x in json.load(sys.stdin) if x["status"]=="deployed"]; print(r[-1]["revision"] if r else 0)')
smoke() {
  timeout 240 env LYNK_BASE_URL=https://lynk.codes LYNK_SMOKE_AWS=true LYNK_SMOKE_SSM=true LYNK_FAILURE_TESTS=false python3 smoke.py
}
if [[ "$action" == rollback ]]; then
  [[ "$revision" -gt 0 ]] || exit 2
  # Require a known successful release/revision pair; no schema rollback.
  python3 - "$state/success.jsonl" "$sha" "$revision" <<'PY'
import json, sys
rows=[json.loads(x) for x in open(sys.argv[1])]
assert any(x['commit']==sys.argv[2] and x['revision']==int(sys.argv[3]) for x in rows), 'Unknown successful release'
PY
  helm rollback lynk-services "$revision" -n lynk-aws --wait --timeout 10m
  smoke
else
  # Download once, sequentially, before migration or Pod replacement.
  while IFS= read -r image; do timeout 300 k3s ctr images pull "$image"; done < <(python3 -c 'import json; print("\n".join(x["image"]["repository"]+"@"+x["image"]["digest"] for x in json.load(open("release.json"))["images"].values()))')
  helm lint chart -f values-aws.yaml -f images.json
  if ! helm upgrade --install lynk-services chart -n lynk-aws -f values-aws.yaml -f images.json --wait --timeout 10m --history-max 20; then
    echo 'Upgrade failed; restoring previous application revision (DB unchanged)'
    if [[ "$previous" -gt 0 ]]; then
      helm rollback lynk-services "$previous" -n lynk-aws --wait --timeout 10m
      smoke || echo "Rollback acceptance failed"
    fi
    exit 1
  fi
  if ! smoke; then
    echo 'Smoke failed; restoring previous application revision (DB unchanged)'
    [[ "$previous" -gt 0 ]] && helm rollback lynk-services "$previous" -n lynk-aws --wait --timeout 10m
    # Previous chart can have different smoke behavior; use same public acceptance.
    smoke || { echo 'Rollback acceptance also failed'; exit 1; }
    exit 1
  fi
fi
current=$(helm history lynk-services -n lynk-aws -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)[-1]["revision"])')
python3 - "$state/success.jsonl" "$sha" "$current" <<'PY'
import datetime,json,sys
with open(sys.argv[1], 'a') as f:
    f.write(json.dumps({'commit':sys.argv[2],'revision':int(sys.argv[3]),'at':datetime.datetime.now(datetime.timezone.utc).isoformat()})+'\n')
PY
printf 'PASS: %s commit=%s revision=%s\n' "$action" "$sha" "$current"
