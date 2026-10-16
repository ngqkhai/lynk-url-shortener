#!/usr/bin/env python3
"""Assert safe initial adoption policy for aws-demo GitOps resources."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def main():
    app = yaml.safe_load((ROOT / "gitops/aws-demo-application.yaml").read_text())
    project = yaml.safe_load((ROOT / "gitops/aws-demo-project.yaml").read_text())
    policy = app["spec"].get("syncPolicy", {})
    assert app["spec"]["destination"]["namespace"] == "lynk-aws"
    assert "automated" not in policy
    assert not policy.get("prune", False)
    assert not policy.get("selfHeal", False)
    sources = app["spec"]["sources"]
    assert len(sources) == 2
    chart, values = sources
    repo = "https://github.com/ngqkhai/lynk-url-shortener.git"
    assert chart["repoURL"] == repo
    assert chart["targetRevision"] == "87eb22600c545ac6952d472739b0091f5bd84281"
    assert chart["path"] == "infra/k8s/helm/lynk-services"
    assert chart["helm"]["valueFiles"] == [
        "values-aws.yaml",
        "$values/infra/k8s/helm/lynk-services/values-aws-demo.yaml",
    ]
    assert values == {"repoURL": repo, "targetRevision": "main", "ref": "values"}
    assert project["spec"]["clusterResourceWhitelist"] == []
    print("PASS: aws-demo adoption remains manual, non-pruning and pinned to the chart/hook source commit")


if __name__ == "__main__":
    main()
