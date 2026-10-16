#!/usr/bin/env python3
"""Fail-closed checks for a single-file release promotion commit."""

import argparse
import re
import subprocess
import sys

ALLOWED_PATH = "infra/k8s/helm/lynk-services/values-aws-demo.yaml"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def require_fresh_source(source_sha: str, main_sha: str) -> None:
    if not SHA_RE.fullmatch(source_sha) or not SHA_RE.fullmatch(main_sha):
        raise ValueError("source and main revisions must be full lowercase commit SHAs")
    if source_sha != main_sha:
        raise ValueError("release source is stale; refusing to promote onto a newer main")


def changed_paths(staged: bool = True) -> list[str]:
    args = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"] if staged else ["git", "diff", "--name-only"]
    output = subprocess.check_output(args, text=True)
    return sorted(path for path in output.splitlines() if path)


def require_only_values_path(paths: list[str]) -> None:
    if paths != [ALLOWED_PATH]:
        raise ValueError("promotion must stage exactly the approved aws-demo values file")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--check-staged", action="store_true")
    args = parser.parse_args()
    require_fresh_source(args.source_sha, args.main_sha)
    if args.check_staged:
        require_only_values_path(changed_paths())
    print("Promotion guard passed: fresh source and allowlisted changes")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Promotion refused: {exc}", file=sys.stderr)
        sys.exit(1)
