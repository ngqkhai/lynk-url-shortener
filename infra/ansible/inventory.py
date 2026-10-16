#!/usr/bin/env python3
"""Resolve one Lynk SSM host from the initialized Terraform output contract."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def inventory_from_outputs(outputs):
    required = ["instance_id", "artifact_bucket", "region"]
    values = {}
    for name in required:
        entry = outputs[name]
        if entry.get("sensitive") is not False or entry.get("type") != "string":
            raise ValueError("Expected non-sensitive string metadata: " + name)
        values[name] = entry["value"]
    if not re.fullmatch(r"i-[0-9a-f]{17}", values["instance_id"]):
        raise ValueError("Invalid EC2 instance ID")
    if not re.fullmatch(r"lynk-k3s-dev-artifactbucket-[a-z0-9]+", values["artifact_bucket"]):
        raise ValueError("Unexpected SSM transport bucket")
    if values["region"] != "ap-southeast-1":
        raise ValueError("Unexpected AWS region")
    host = {
        "ansible_host": values["instance_id"],
        "ansible_connection": "amazon.aws.aws_ssm",
        "ansible_aws_ssm_region": values["region"],
        "ansible_aws_ssm_bucket_name": values["artifact_bucket"],
        "ansible_python_interpreter": "/usr/bin/python3",
        "ansible_become": True,
        "ansible_become_user": "root",
    }
    return {"_meta": {"hostvars": {"lynk": host}}, "all": {"hosts": ["lynk"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--host")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "terraform/environments/aws-demo"
    try:
        result = subprocess.run(
            [os.environ.get("LYNK_TERRAFORM", "terraform"), "-chdir=" + str(root), "output", "-json"],
            capture_output=True, text=True, check=True, timeout=60,
        )
        inventory = inventory_from_outputs(json.loads(result.stdout))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("Inventory unavailable: initialize aws-demo Terraform backend and verify AWS authentication/outputs", file=sys.stderr)
        return 1
    if args.list:
        print(json.dumps(inventory))
    else:
        print(json.dumps(inventory["_meta"]["hostvars"].get(args.host, {})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
