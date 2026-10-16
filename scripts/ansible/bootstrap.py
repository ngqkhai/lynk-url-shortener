#!/usr/bin/env python3
"""Own controller plaintext lifetime while Ansible converges host configuration."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def run_bootstrap(password_arguments, check=False, executable="ansible-playbook", vault="ansible-vault", runner=subprocess.run):
    os.umask(0o077)
    inventory_script = ROOT / "infra/ansible/inventory.py"
    inventory_result = runner(
        [sys.executable, str(inventory_script), "--list"],
        capture_output=True, text=True,
    )
    if inventory_result.returncode != 0:
        raise RuntimeError("Terraform inventory could not resolve a host; initialize the backend and verify AWS access")
    try:
        hosts = json.loads(inventory_result.stdout).get("all", {}).get("hosts", [])
    except (ValueError, AttributeError):
        raise RuntimeError("Terraform inventory returned invalid host metadata") from None
    if hosts != ["lynk"]:
        raise RuntimeError("Terraform inventory must resolve exactly the Lynk host")
    # The controller owns cleanup even if Ansible reports host unreachable.
    # SIGKILL/controller loss cannot run finally; temp permissions still apply.
    with tempfile.TemporaryDirectory(prefix="lynk-bootstrap-") as directory:
        root = Path(directory)
        ansible_tmp = root / "ansible-tmp"
        ansible_tmp.mkdir(mode=0o700)
        secret_dir = root / "runtime"
        restored = runner(
            [sys.executable, str(ROOT / "scripts/secrets/vault-bundle.py"), "restore",
             "--ansible-vault", vault, "--output-dir", str(secret_dir), *password_arguments],
            capture_output=True, text=True,
        )
        if restored.returncode != 0:
            raise RuntimeError("Vault restoration failed; details suppressed")
        variables = root / "variables.json"
        variables.write_text(json.dumps({"lynk_secrets_dir": str(secret_dir)}))
        command = [
            executable, "-i", str(inventory_script),
            str(ROOT / "infra/ansible/bootstrap.yml"), "--extra-vars", "@" + str(variables),
        ]
        if check:
            command.append("--check")
        # No capture: Ansible task output is useful; secret tasks use no_log.
        environment = os.environ.copy()
        environment["ANSIBLE_LOCAL_TEMP"] = str(ansible_tmp)
        result = runner(command, env=environment)
        return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    password = parser.add_mutually_exclusive_group(required=True)
    password.add_argument("--password-file")
    password.add_argument("--password-env")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    executable = shutil.which("ansible-playbook")
    vault = shutil.which("ansible-vault")
    if not executable or not vault or not shutil.which("session-manager-plugin"):
        parser.error("Pinned Ansible and Session Manager plugin must be on controller PATH")
    password_arguments = ["--password-file", args.password_file] if args.password_file else ["--password-env", args.password_env]
    try:
        return run_bootstrap(password_arguments, args.check, executable, vault)
    except (RuntimeError, OSError):
        print("Bootstrap controller failed; temporary plaintext cleaned when process exited normally", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
