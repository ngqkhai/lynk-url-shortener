#!/usr/bin/env python3
"""Render and check the non-mutating aws-demo Helm source contract."""

from pathlib import Path
import os
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "infra/k8s/helm/lynk-services"
VALUES = CHART / "values-aws-demo.yaml"
HELM = os.environ.get("HELM_BINARY", "helm")
EXPECTED = {
    "urlService": "sha256:1d916376cf6afce9c98e6a4517e2dfb2356b285c1cd2d02c62e55a487e70c978",
    "redirectService": "sha256:8bec2f41a7431722f156d6447bd13c9dfe5d54fedd771566b531661d1ee11e82",
    "authService": "sha256:f4e2964249d4c3679807ae5d315b34831e0bbdf7970119da830b74f42f8fd65c",
}


def main():
    values = yaml.safe_load(VALUES.read_text())
    assert values["global"]["migrationHookMode"] == "argocd"
    assert values["global"]["imageTag"] == "b6cc75a477df508eadda3b0f57d9a9994b304a11"
    for service, digest in EXPECTED.items():
        assert values[service]["image"]["digest"] == digest
        assert values[service]["image"]["pullPolicy"] == "IfNotPresent"

    subprocess.run(
        [HELM, "lint", str(CHART), "-f", str(CHART / "values-aws.yaml"), "-f", str(VALUES)],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )
    rendered = subprocess.check_output(
        [
            HELM,
            "template",
            "lynk-services",
            str(CHART),
            "--namespace",
            "lynk-aws",
            "-f",
            str(CHART / "values-aws.yaml"),
            "-f",
            str(VALUES),
        ],
        cwd=ROOT,
        text=True,
    )
    objects = [item for item in yaml.safe_load_all(rendered) if item]
    by_kind_name = {(item["kind"], item["metadata"]["name"]): item for item in objects}
    for service, digest in EXPECTED.items():
        deployment = by_kind_name[("Deployment", service.replace("Service", "-service"))]
        image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
        assert image.endswith("@" + digest), (service, image)

    migrations = [
        item
        for item in objects
        if item["kind"] == "Job" and item["metadata"].get("annotations", {}).get("argocd.argoproj.io/hook") == "PreSync"
    ]
    assert {item["metadata"]["name"] for item in migrations} == {
        "url-service-migrate",
        "redirect-service-migrate",
        "auth-service-migrate",
    }
    smoke = by_kind_name[("Job", "lynk-postsync-smoke")]
    assert smoke["metadata"]["annotations"]["argocd.argoproj.io/hook"] == "PostSync"
    script = smoke["spec"]["template"]["spec"]["containers"][0]["args"][0]
    for service in ("url-service:3001", "redirect-service:3002", "auth-service:3004"):
        assert f"http://{service}/health/ready" in script
    assert "DATABASE_URL" not in script and "password" not in script.lower()
    namespaced_kinds = {"Deployment", "Ingress", "Job", "Middleware", "Service"}
    assert objects and all(item["kind"] in namespaced_kinds for item in objects)
    assert all(item["metadata"].get("namespace", "lynk-aws") == "lynk-aws" for item in objects)
    print("PASS: aws-demo chart renders three digest-pinned services, three PreSync migrations and one PostSync readiness smoke")


if __name__ == "__main__":
    main()
