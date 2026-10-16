#!/usr/bin/env python3
"""Install the pinned, signature-verified controller plugin into a private prefix."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((ROOT / "infra/ansible/controller/tools.json").read_text())["session_manager_plugin"]
    os.umask(0o077)
    args.prefix.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lynk-ssm-install-") as directory:
        root = Path(directory)
        archive = root / "plugin.deb"
        signature = root / "plugin.deb.sig"
        archive.write_bytes(urllib.request.urlopen(lock["url"], timeout=60).read())
        signature.write_bytes(urllib.request.urlopen(lock["url"] + ".sig", timeout=30).read())
        if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["sha256"]:
            raise RuntimeError("Plugin package checksum mismatch")
        keyring = root / "gnupg"
        keyring.mkdir(mode=0o700)
        subprocess.run(
            ["gpg", "--batch", "--homedir", str(keyring), "--import", str(ROOT / "infra/ansible/controller/ssm-signer.asc")],
            check=True, capture_output=True,
        )
        verified = subprocess.run(
            ["gpg", "--batch", "--homedir", str(keyring), "--status-fd", "1", "--verify", str(signature), str(archive)],
            check=True, capture_output=True, text=True,
        )
        if "[GNUPG:] VALIDSIG " + lock["signer_fingerprint"] + " " not in verified.stdout:
            raise RuntimeError("Unexpected Session Manager plugin signer")
        subprocess.run(["dpkg-deb", "--extract", str(archive), str(args.prefix)], check=True)
    executable = args.prefix / "usr/local/sessionmanagerplugin/bin/session-manager-plugin"
    version = subprocess.check_output([str(executable), "--version"], text=True).strip()
    if version != lock["version"]:
        raise RuntimeError("Extracted plugin version mismatch")
    if os.environ.get("GITHUB_PATH"):
        with Path(os.environ["GITHUB_PATH"]).open("a") as output:
            output.write(str(executable.parent) + "\n")
    print(json.dumps({"version": version, "signature_verified": True, "executable": str(executable)}))


if __name__ == "__main__":
    main()
