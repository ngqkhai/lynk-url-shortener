#!/usr/bin/env python3
"""Exercise S3 locking and version recovery using only isolated fixture state."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not re.fullmatch(
        r"lynk-tfstate-231136241975-ap-southeast-1-[a-z0-9-]+", args.bucket
    ):
        parser.error("Expected a dedicated Lynk state bucket in the verified account")

    os.umask(0o077)
    prefix = "verification/cp04/" + uuid.uuid4().hex
    key = prefix + "/terraform.tfstate"
    recovery_key = prefix + "/recovered.tfstate"
    aws_command = ["aws", "--region", "ap-southeast-1"]

    def run(command, cwd=None, check=True):
        return subprocess.run(
            command, cwd=cwd, check=check, capture_output=True, text=True, timeout=60
        )

    def aws(*arguments):
        return run(aws_command + list(arguments)).stdout

    account = json.loads(aws("sts", "get-caller-identity"))["Account"]
    if account != "231136241975":
        raise RuntimeError("AWS account mismatch; no fixture state was written")

    with tempfile.TemporaryDirectory(prefix="lynk-cp04-") as directory:
        root = Path(directory)
        original = root / "original"
        recovered = root / "recovered"
        original.mkdir(mode=0o700)
        recovered.mkdir(mode=0o700)
        fixture = '''terraform {
  required_version = "= 1.16.6"
  backend "s3" {}
}
variable "value" { type = string }
resource "terraform_data" "fixture" {
  input = var.value
  provisioner "local-exec" {
    command = "sleep 15"
  }
}
output "value" { value = terraform_data.fixture.output }
'''
        for path, state_key in [(original, key), (recovered, recovery_key)]:
            (path / "main.tf").write_text(fixture)
            config = {
                "bucket": args.bucket,
                "key": state_key,
                "region": "ap-southeast-1",
                "encrypt": True,
                "use_lockfile": True,
                "allowed_account_ids": [account],
            }
            (path / "backend.json").write_text(json.dumps(config))
            run(
                [args.terraform, "init", "-input=false", "-backend-config=backend.json"],
                cwd=path,
            )

        owner_command = [
            args.terraform, "apply", "-input=false", "-auto-approve", "-var=value=v1"
        ]
        with (root / "owner.log").open("w+") as owner_log:
            owner = subprocess.Popen(
                owner_command, cwd=original, stdout=owner_log, stderr=subprocess.STDOUT
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    lock = run(
                        aws_command + [
                            "s3api", "head-object", "--bucket", args.bucket,
                            "--key", key + ".tflock",
                        ], check=False,
                    )
                    if lock.returncode == 0:
                        break
                    if owner.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Fixture owner failed or lock was not observed")
                    time.sleep(0.25)
                contender = run(
                    [args.terraform, "plan", "-input=false", "-lock-timeout=1s", "-var=value=v1"],
                    cwd=original, check=False,
                )
                if contender.returncode == 0 or "Error acquiring the state lock" not in (
                    contender.stdout + contender.stderr
                ):
                    raise RuntimeError("Concurrent writer did not fail on the fixture lock")
            finally:
                # Let Terraform finish and release its own lock, including on assertion failure.
                owner.wait(timeout=60)
            if owner.returncode != 0:
                raise RuntimeError("Fixture owner apply failed; inspect isolated state before retry")

        v1 = json.loads(run([args.terraform, "state", "pull"], cwd=original).stdout)
        versions = json.loads(aws(
            "s3api", "list-object-versions", "--bucket", args.bucket, "--prefix", key
        ))["Versions"]
        first_version = next(
            version["VersionId"] for version in versions
            if version["Key"] == key and version["IsLatest"]
        )
        run(
            [args.terraform, "apply", "-input=false", "-auto-approve", "-var=value=v2"],
            cwd=original,
        )
        v2 = json.loads(run([args.terraform, "state", "pull"], cwd=original).stdout)
        archive = root / "v1.tfstate"
        aws(
            "s3api", "get-object", "--bucket", args.bucket, "--key", key,
            "--version-id", first_version, str(archive),
        )
        if json.loads(archive.read_text()) != v1:
            raise RuntimeError("Versioned object differs from original v1 state")
        aws(
            "s3api", "put-object", "--bucket", args.bucket, "--key", recovery_key,
            "--body", str(archive), "--server-side-encryption", "AES256",
        )
        restored = json.loads(run([args.terraform, "state", "pull"], cwd=recovered).stdout)
        current = json.loads(run([args.terraform, "state", "pull"], cwd=original).stdout)
        if not (
            restored == v1 and current == v2
            and v1["outputs"]["value"]["value"] == "v1"
            and v2["outputs"]["value"]["value"] == "v2"
            and v2["serial"] > v1["serial"]
            and v2["lineage"] == v1["lineage"]
        ):
            raise RuntimeError("Recovery verification failed")

        result = {
            "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "bucket": args.bucket,
            "fixture_key": key,
            "recovery_key": recovery_key,
            "recovered_version_id": first_version,
            "lock_observed": True,
            "concurrent_writer_rejected": True,
            "owner_completed": True,
            "recovered_state_equal_to_v1": True,
            "original_key_unchanged_by_recovery": True,
            "serial_v1": v1["serial"],
            "serial_v2": v2["serial"],
            "scope": "provider-free terraform_data fixture; no application or bootstrap state",
            "retained": "Fixture objects/versions retained under verification prefix for audit",
        }
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
