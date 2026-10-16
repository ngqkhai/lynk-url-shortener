#!/usr/bin/env python3
"""Emit a secret-free identity snapshot of live aws-demo workload resources."""

import argparse
import json
import subprocess


parser = argparse.ArgumentParser()
parser.add_argument("--kubectl", default="/usr/local/bin/kubectl")
parser.add_argument("--namespace", default="lynk-aws")
args = parser.parse_args()


def get(kind):
    raw = subprocess.check_output(
        [args.kubectl, "get", kind, "-n", args.namespace, "-o", "json"], text=True
    )
    return json.loads(raw)["items"]


def metadata(obj):
    value = obj["metadata"]
    return {
        "name": value["name"],
        "uid": value["uid"],
        "generation": value.get("generation"),
        "resourceVersion": value.get("resourceVersion"),
    }


snapshot = {"namespace": args.namespace}
for kind in ("deployments", "statefulsets"):
    rows = []
    for obj in get(kind):
        pod_spec = obj["spec"]["template"]["spec"]
        rows.append(
            {
                **metadata(obj),
                "replicas": obj["spec"].get("replicas", 1),
                "containers": sorted(
                    (
                        container["name"],
                        container["image"],
                        container.get("resources", {}).get("requests", {}),
                        container.get("resources", {}).get("limits", {}),
                    )
                    for container in pod_spec.get("containers", [])
                ),
                "readyReplicas": obj.get("status", {}).get("readyReplicas", 0),
                "secretRefs": sorted(
                    {
                        volume["secret"]["secretName"]
                        for volume in pod_spec.get("volumes", [])
                        if volume.get("secret", {}).get("secretName")
                    }
                    | {
                        env["valueFrom"]["secretKeyRef"]["name"]
                        for container in pod_spec.get("containers", [])
                        for env in container.get("env", [])
                        if env.get("valueFrom", {}).get("secretKeyRef", {}).get("name")
                    }
                ),
            }
        )
    snapshot[kind] = sorted(rows, key=lambda item: item["name"])

pods = []
for obj in get("pods"):
    statuses = obj.get("status", {}).get("containerStatuses", [])
    pods.append(
        {
            **metadata(obj),
            "ownerReferences": sorted(
                (owner["kind"], owner["name"]) for owner in obj["metadata"].get("ownerReferences", [])
            ),
            "containers": sorted(
                (item["name"], item.get("imageID"), item.get("ready"), item.get("restartCount"))
                for item in statuses
            ),
        }
    )
snapshot["pods"] = sorted(pods, key=lambda item: item["name"])

for kind in ("services", "ingresses", "persistentvolumeclaims", "jobs"):
    rows = []
    for obj in get(kind):
        value = {**metadata(obj)}
        if kind == "services":
            value.update(
                {
                    "type": obj["spec"].get("type"),
                    "clusterIP": obj["spec"].get("clusterIP"),
                    "selector": obj["spec"].get("selector", {}),
                    "ports": obj["spec"].get("ports", []),
                }
            )
        elif kind == "ingresses":
            value["rules"] = obj["spec"].get("rules", [])
        elif kind == "persistentvolumeclaims":
            value.update(
                {
                    "phase": obj.get("status", {}).get("phase"),
                    "volumeName": obj["spec"].get("volumeName"),
                    "storageClassName": obj["spec"].get("storageClassName"),
                    "accessModes": obj["spec"].get("accessModes", []),
                }
            )
        elif kind == "jobs":
            status = obj.get("status", {})
            value.update({"succeeded": status.get("succeeded", 0), "active": status.get("active", 0)})
        rows.append(value)
    snapshot[kind] = sorted(rows, key=lambda item: item["name"])

print(json.dumps(snapshot, sort_keys=True, separators=(",", ":")))
