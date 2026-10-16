#!/usr/bin/env python3
"""Check the aws-demo Argo Project/Application contract without cluster access."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def check():
    project_path = ROOT / 'gitops/aws-demo-project.yaml'
    application_path = ROOT / 'gitops/aws-demo-application.yaml'
    project = yaml.safe_load(project_path.read_text())
    application = yaml.safe_load(application_path.read_text())
    assert project['apiVersion'] == 'argoproj.io/v1alpha1' and project['kind'] == 'AppProject'
    assert application['apiVersion'] == 'argoproj.io/v1alpha1' and application['kind'] == 'Application'
    assert (project['metadata']['namespace'], project['metadata']['name']) == ('argocd', 'aws-demo')
    assert (application['metadata']['namespace'], application['metadata']['name']) == ('argocd', 'aws-demo')

    spec = application['spec']
    repo = 'https://github.com/ngqkhai/lynk-url-shortener.git'
    server = 'https://kubernetes.default.svc'
    assert spec['project'] == 'aws-demo'
    assert 'source' not in spec
    assert len(spec['sources']) == 2
    chart_source, values_source = spec['sources']
    assert chart_source['repoURL'] == repo
    assert len(chart_source['targetRevision']) == 40 and all(c in '0123456789abcdef' for c in chart_source['targetRevision'])
    assert chart_source['path'] == 'infra/k8s/helm/lynk-services'
    assert chart_source['helm']['valueFiles'] == [
        'values-aws.yaml', '$values/infra/k8s/helm/lynk-services/values-aws-demo.yaml'
    ]
    assert values_source == {'repoURL': repo, 'targetRevision': 'main', 'ref': 'values'}
    assert spec['destination'] == {'server': server, 'namespace': 'lynk-aws'}
    policy = spec.get('syncPolicy', {})
    assert 'automated' not in policy
    assert policy.get('prune', False) is False and policy.get('selfHeal', False) is False
    assert project['spec']['sourceRepos'] == [repo]
    assert project['spec']['destinations'] == [{'server': server, 'namespace': 'lynk-aws'}]
    assert project['spec']['clusterResourceWhitelist'] == []
    allowed = {(item['group'], item['kind']) for item in project['spec']['namespaceResourceWhitelist']}
    assert allowed == {('', 'Service'), ('apps', 'Deployment'), ('batch', 'Job'),
                       ('networking.k8s.io', 'Ingress'), ('traefik.io', 'Middleware')}
    chart = (ROOT / chart_source['path']).resolve()
    assert chart.is_relative_to(ROOT) and (chart / 'Chart.yaml').is_file()
    for value_file in chart_source['helm']['valueFiles']:
        if value_file.startswith('$values/'):
            resolved = (ROOT / value_file.removeprefix('$values/')).resolve()
        else:
            resolved = (chart / value_file).resolve()
        assert resolved.is_relative_to(ROOT) and resolved.is_file()

    old_examples = [ROOT / 'gitops/argocd-application.yaml', ROOT / 'gitops/redis-application.yaml']
    assert not any(path.exists() for path in old_examples)
    print('PASS: aws-demo Project and pinned Application source contracts; manual sync, no prune (not a cluster health check)')


if __name__ == '__main__':
    check()
