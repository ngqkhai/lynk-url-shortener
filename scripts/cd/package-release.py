#!/usr/bin/env python3
"""Build a secret-free, digest-pinned release from CI image metadata."""
import argparse
import json
import re
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--sha', required=True)
parser.add_argument('--metadata', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
a = parser.parse_args()
assert re.fullmatch(r'[0-9a-f]{40}', a.sha), 'Invalid commit SHA'
a.output.mkdir(parents=True, exist_ok=False)
images = {}
for service in ['url', 'redirect', 'auth']:
    data = json.loads((a.metadata / (service + '.json')).read_text())
    assert data['repository'] == 'ghcr.io/ngqkhai/lynk-' + service + '-service'
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', data['digest'])
    images[service + 'Service'] = { 'image': {**data, 'pullPolicy': 'IfNotPresent'} }
shutil.copytree('infra/k8s/helm/lynk-services', a.output / 'chart')
shutil.copy('infra/k8s/helm/lynk-services/values-aws.yaml', a.output / 'values-aws.yaml')
shutil.copy('scripts/smoke-sprint3a.py', a.output / 'smoke.py')
(a.output / 'images.json').write_text(json.dumps({'global': {'imageTag': a.sha}, **images}))
(a.output / 'release.json').write_text(json.dumps({'version': 1, 'commit': a.sha, 'images': images}, indent=2))
