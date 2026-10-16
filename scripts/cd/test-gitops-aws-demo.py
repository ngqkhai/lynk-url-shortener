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
    assert policy["automated"] == {"selfHeal": True, "prune": False}
    assert app["spec"]["source"]["targetRevision"] == "aws-demo"
    assert project["spec"]["clusterResourceWhitelist"] == []
    print("PASS: aws-demo follows its dedicated branch, self-heals drift and keeps pruning disabled")


if __name__ == "__main__":
    main()
