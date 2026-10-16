#!/usr/bin/env python3
"""Apply validated immutable image digests to one aws-demo values file."""

import argparse
import json
import re
import sys
import os
import tempfile
from pathlib import Path

import yaml


EXPECTED_REPOSITORIES = {
    "urlService": "ghcr.io/ngqkhai/lynk-url-service",
    "redirectService": "ghcr.io/ngqkhai/lynk-redirect-service",
    "authService": "ghcr.io/ngqkhai/lynk-auth-service",
}
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
ALLOWED_VALUES_PATH = "infra/k8s/helm/lynk-services/values-aws-demo.yaml"


def validate_release(release: dict, expected_sha: str) -> dict[str, str]:
    if not SHA_RE.fullmatch(expected_sha) or release.get("version") != 1:
        raise ValueError("unsupported release schema or commit SHA")
    if release.get("commit") != expected_sha:
        raise ValueError("release manifest commit does not match the workflow source SHA")
    images = release.get("images")
    if not isinstance(images, dict) or set(images) != set(EXPECTED_REPOSITORIES):
        raise ValueError("release manifest must contain exactly the three Lynk service images")

    digests = {}
    for service, repository in EXPECTED_REPOSITORIES.items():
        service_data = images[service]
        image = service_data.get("image", {}) if isinstance(service_data, dict) else {}
        if not isinstance(image, dict):
            raise ValueError(f"invalid image metadata for {service}")
        if image.get("repository") != repository or not DIGEST_RE.fullmatch(image.get("digest", "")):
            raise ValueError(f"invalid repository or digest for {service}")
        digests[service] = image["digest"]
    return digests


def promoted_values(values: dict, release: dict, expected_sha: str) -> dict:
    digests = validate_release(release, expected_sha)
    if not isinstance(values, dict) or not isinstance(values.get("global"), dict):
        raise ValueError("aws-demo values must contain a global mapping")
    values["global"]["imageTag"] = expected_sha
    for service, digest in digests.items():
        image = values.get(service, {}).get("image")
        if not isinstance(image, dict) or image.get("repository") != EXPECTED_REPOSITORIES[service]:
            raise ValueError(f"aws-demo values contain an unexpected repository for {service}")
        image["digest"] = digest
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True, type=Path)
    parser.add_argument("--values", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    if args.values.resolve() != (root / ALLOWED_VALUES_PATH).resolve():
        parser.error(f"values path must be exactly {ALLOWED_VALUES_PATH}")

    release = json.loads(args.release_json.read_text(encoding="utf-8"))
    values = yaml.safe_load(args.values.read_text(encoding="utf-8"))
    updated = promoted_values(values, release, args.expected_sha)
    output = yaml.safe_dump(updated, sort_keys=False, allow_unicode=True, default_flow_style=False)
    previous = args.values.read_text(encoding="utf-8")
    if output != previous:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.values.parent, delete=False) as temp:
            temp.write(output)
            temp.flush()
            os.fsync(temp.fileno())
            temporary_path = Path(temp.name)
        os.replace(temporary_path, args.values)
    print(json.dumps({"commit": args.expected_sha, "images": validate_release(release, args.expected_sha)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValueError) as exc:
        print(f"Promotion refused: {exc}", file=sys.stderr)
        sys.exit(1)
