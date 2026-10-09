#!/usr/bin/env python3
"""Check the current Application source contracts without applying them to a cluster."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def check():
    identities = set()
    paths = sorted((ROOT / 'gitops').rglob('*.yaml'))
    if not paths:
        raise ValueError('No GitOps manifests found')
    for path in paths:
        for manifest in yaml.safe_load_all(path.read_text()):
            if not isinstance(manifest, dict):
                raise ValueError(f'{path.relative_to(ROOT)}: expected a manifest object')
            if manifest.get('apiVersion') != 'argoproj.io/v1alpha1' or manifest.get('kind') != 'Application':
                raise ValueError(f'{path.relative_to(ROOT)}: expected an ArgoCD Application')
            metadata = manifest['metadata']
            identity = (metadata['namespace'], metadata['name'])
            if identity in identities:
                raise ValueError(f'Duplicate Application: {identity}')
            identities.add(identity)
            spec = manifest['spec']
            source = spec['source']
            for value in (spec['project'], source['repoURL'], source['targetRevision'],
                          spec['destination']['server'], spec['destination']['namespace'], *identity):
                if not isinstance(value, str) or not value:
                    raise ValueError(f'{path.relative_to(ROOT)}: missing string field')
            if bool(source.get('path')) == bool(source.get('chart')):
                raise ValueError(f'{path.relative_to(ROOT)}: specify either path or chart')
            if source.get('path') and source['repoURL'] == 'https://github.com/ngqkhai/lynk-url-shortener.git':
                chart = (ROOT / source['path']).resolve()
                if not chart.is_relative_to(ROOT) or not (chart / 'Chart.yaml').is_file():
                    raise ValueError(f'{path.relative_to(ROOT)}: missing local Helm chart')
                for value_file in source.get('helm', {}).get('valueFiles', []):
                    resolved = (chart / value_file).resolve()
                    if not resolved.is_relative_to(ROOT) or not resolved.is_file():
                        raise ValueError(f'{path.relative_to(ROOT)}: missing values file')
    print(f'PASS: {len(identities)} Application source contracts (not a cluster health check)')


if __name__ == '__main__':
    check()
