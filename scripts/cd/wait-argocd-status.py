#!/usr/bin/env python3
"""Send a read-only SSM status request and wait for its one plugin result."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TERMINAL = {"Success", "Cancelled", "TimedOut", "Failed", "DeliveryTimedOut", "ExecutionTimedOut"}
RETRYABLE_VISIBILITY = ("InvocationDoesNotExist", "Invocation does not exist")


def aws_json(*args):
    completed = subprocess.run(["aws", *args, "--output", "json"], capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "AWS CLI request failed")
    return json.loads(completed.stdout)


def wait_for_command(command_id, instance_id, deadline, get_invocation=aws_json, sleep=time.sleep, clock=time.monotonic):
    while clock() < deadline:
        try:
            result = get_invocation("ssm", "get-command-invocation", "--command-id", command_id, "--instance-id", instance_id)
        except RuntimeError as exc:
            message = str(exc)
            if not any(marker in message for marker in RETRYABLE_VISIBILITY):
                raise
            sleep(min(5, max(0, deadline - clock())))
            continue
        status = result.get("Status")
        if status == "Success":
            output = result.get("StandardOutputContent", "").strip()
            try:
                summary = json.loads(output)
            except json.JSONDecodeError as exc:
                raise RuntimeError("status document returned no valid summary") from exc
            if summary.get("status") != "Healthy" or summary.get("smoke") != "Succeeded":
                raise RuntimeError("status document did not confirm Healthy and smoke success")
            return summary
        if status in TERMINAL:
            raise RuntimeError(f"read-only status command ended with {status}")
        if status not in ("Pending", "InProgress", "Delayed", "Cancelling"):
            raise RuntimeError(f"unexpected SSM invocation status: {status}")
        sleep(min(5, max(0, deadline - clock())))
    raise TimeoutError("SSM status polling deadline exceeded")


def main():
    release_path = Path(os.environ.get("RELEASE_JSON", "release-artifact/extracted/release.json"))
    release = json.loads(release_path.read_text())
    sha = os.environ["RELEASE_SHA"]
    revision = os.environ["VALUES_REVISION"]
    instance = os.environ["INSTANCE_ID"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("invalid release or promotion revision")
    if release.get("commit") != sha or not re.fullmatch(r"i-[0-9a-f]+", instance):
        raise ValueError("release manifest or instance does not match workflow context")
    images = release["images"]
    args = {
        "ValuesRevision": revision,
        "ReleaseSha": sha,
        "UrlDigest": images["urlService"]["image"]["digest"],
        "RedirectDigest": images["redirectService"]["image"]["digest"],
        "AuthDigest": images["authService"]["image"]["digest"],
    }
    command = aws_json("ssm", "send-command", "--instance-ids", instance, "--document-name", "LynkArgoStatus",
                       "--parameters", json.dumps({key: [value] for key, value in args.items()}))["Command"]["CommandId"]
    result = wait_for_command(command, instance, time.monotonic() + 930)
    if result.get("values_revision") != revision or result.get("release_sha") != sha:
        raise RuntimeError("status output does not match the requested promotion/release")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Argo status verification failed: {exc}", file=sys.stderr)
        sys.exit(1)
