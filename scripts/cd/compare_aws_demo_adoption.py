#!/usr/bin/env python3
"""Assert an Argo adoption sync preserved protected aws-demo resource identities."""

import argparse
import json
from pathlib import Path

EXPECTED_HOOK_JOBS = {
    "auth-service-migrate",
    "redirect-service-migrate",
    "url-service-migrate",
    "lynk-postsync-smoke",
}


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def keyed(rows: list[dict], fields: tuple[str, ...]) -> dict[str, tuple]:
    return {
        item["name"]: tuple(item.get(field) for field in fields)
        for item in rows
    }


def compare(before: dict, after: dict, allow_pending_hooks: bool = False) -> None:
    if before.get("namespace") != after.get("namespace"):
        raise ValueError("namespace changed during adoption")

    for collection, fields in {
        "deployments": ("uid", "replicas", "containers"),
        "statefulsets": ("uid", "replicas", "containers"),
        "services": ("uid", "type", "clusterIP", "selector", "ports"),
        "ingresses": ("uid", "rules"),
        "persistentvolumeclaims": ("uid", "phase", "volumeName", "storageClassName", "accessModes"),
    }.items():
        if keyed(before.get(collection, []), fields) != keyed(after.get(collection, []), fields):
            raise ValueError(f"protected {collection} identity or desired runtime fields changed")

    before_pods = {item["name"]: item for item in before.get("pods", [])}
    after_pods = {item["name"]: item for item in after.get("pods", [])}
    for name, old in before_pods.items():
        new = after_pods.get(name)
        if not new:
            raise ValueError("pre-existing Pod disappeared during adoption: " + name)
        old_containers = [(row[0], row[1], row[2]) for row in old.get("containers", [])]
        new_containers = [(row[0], row[1], row[2]) for row in new.get("containers", [])]
        if (old["uid"], old.get("ownerReferences"), old_containers) != (
            new["uid"], new.get("ownerReferences"), new_containers
        ):
            raise ValueError("pre-existing Pod identity, image or readiness changed: " + name)

    before_jobs = {item["name"]: item for item in before.get("jobs", [])}
    after_jobs = {item["name"]: item for item in after.get("jobs", [])}
    for name, old in before_jobs.items():
        if name not in after_jobs or old["uid"] != after_jobs[name]["uid"]:
            raise ValueError("pre-existing Job identity changed during adoption: " + name)
    added_jobs = set(after_jobs) - set(before_jobs)
    valid_jobs = added_jobs <= EXPECTED_HOOK_JOBS if allow_pending_hooks else added_jobs == EXPECTED_HOOK_JOBS
    if not valid_jobs:
        raise ValueError("unexpected hook Job set after adoption: " + ", ".join(sorted(added_jobs)))
    if allow_pending_hooks and not {"auth-service-migrate", "redirect-service-migrate", "url-service-migrate"} <= added_jobs:
        raise ValueError("partial adoption is missing one or more expected PreSync migration Jobs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--allow-pending-hooks", action="store_true")
    args = parser.parse_args()
    compare(load(args.before), load(args.after), allow_pending_hooks=args.allow_pending_hooks)
    print("PASS: protected workload/Pod/PVC identities are unchanged; added Jobs are within the reviewed Argo hook set")


if __name__ == "__main__":
    main()
