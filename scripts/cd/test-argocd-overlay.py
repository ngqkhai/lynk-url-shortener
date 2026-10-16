#!/usr/bin/env python3
"""Validate the pinned, non-HA Argo CD CP12 overlay without cluster access."""

import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "infra/argocd"
UPSTREAM = OVERLAY / "upstream/install.yaml"
EXPECTED_SHA256 = "90dc9094bf4c5964afd9c0e35d735e1c2fcbbda4f8e36799c092d9864ed65f50"


def documents(path):
    return [item for item in yaml.safe_load_all(path.read_text()) if item]


def merge_named(items, patch_items, context):
    by_name = {item["name"]: item for item in items}
    for patch in patch_items:
        name = patch["name"]
        if name not in by_name:
            raise AssertionError(f"{context}: unknown container {name}")
        by_name[name].update(patch)


def main():
    digest = hashlib.sha256(UPSTREAM.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256, f"upstream manifest checksum mismatch: {digest}"

    kustomization = yaml.safe_load((OVERLAY / "kustomization.yaml").read_text())
    assert kustomization["namespace"] == "argocd"
    assert set(kustomization["resources"]) == {"namespace.yaml", "upstream/install.yaml"}

    upstream = documents(UPSTREAM)
    assert len(upstream) == 59, f"expected 59 upstream objects, got {len(upstream)}"
    assert not any(obj.get("kind") == "Application" for obj in upstream)
    objects = {(obj["kind"], obj["metadata"]["name"]): obj for obj in upstream}
    patches = {}
    for entry in kustomization["patches"]:
        patch = yaml.safe_load((OVERLAY / entry["path"]).read_text())
        target = entry["target"]
        key = (target["kind"], target["name"])
        assert key in objects, f"patch target does not exist upstream: {key}"
        assert key == (patch["kind"], patch["metadata"]["name"])
        assert key not in patches, f"duplicate workload patch: {key}"
        patches[key] = patch

    workloads = [obj for obj in upstream if obj.get("kind") in {"Deployment", "StatefulSet"}]
    assert len(workloads) == 7
    rendered_image_refs = set()
    for workload in workloads:
        key = (workload["kind"], workload["metadata"]["name"])
        assert workload["spec"].get("replicas", 1) == 1, f"{key}: non-single replica"
        spec = workload["spec"]["template"]["spec"]
        patch_spec = patches[key]["spec"]["template"]["spec"]
        merge_named(spec.get("containers", []), patch_spec.get("containers", []), str(key))
        merge_named(spec.get("initContainers", []), patch_spec.get("initContainers", []), str(key))
        for container in spec.get("containers", []) + spec.get("initContainers", []):
            image = container.get("image", "")
            assert image and ":latest" not in image, f"{key}/{container['name']}: unpinned image"
            rendered_image_refs.add(image)
            resources = container.get("resources", {})
            assert resources.get("requests") and resources.get("limits"), (
                f"{key}/{container['name']}: requests/limits missing"
            )

    assert "quay.io/argoproj/argocd:v3.5.5" in rendered_image_refs
    services = [obj for obj in upstream if obj.get("kind") == "Service"]
    server = next(obj for obj in services if obj["metadata"]["name"] == "argocd-server")
    assert patches[("Service", "argocd-server")]["spec"]["type"] == "ClusterIP"
    assert not any(obj.get("kind") == "Ingress" for obj in upstream)

    tracking = yaml.safe_load((OVERLAY / "patches/argocd-cm.yaml").read_text())
    assert tracking["data"]["application.resourceTrackingMethod"] == "annotation"
    namespace = yaml.safe_load((OVERLAY / "namespace.yaml").read_text())
    assert namespace["kind"] == "Namespace" and namespace["metadata"]["name"] == "argocd"

    port_forward = (ROOT / "infra/ansible/roles/argocd/files/argocd-port-forward.service").read_text()
    assert "--address=127.0.0.1" in port_forward and "8443:443" in port_forward
    assert "--address=0.0.0.0" not in port_forward

    print(
        f"Argo CD v3.5.5 overlay valid: sha256={digest}, "
        f"{len(upstream)} upstream objects, {len(workloads)} single-replica workloads, "
        f"{len(rendered_image_refs)} pinned images, ClusterIP, annotation tracking, no Applications"
    )


if __name__ == "__main__":
    main()
