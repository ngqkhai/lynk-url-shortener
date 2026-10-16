#!/usr/bin/env python3
"""Fail-safe classifier for files included in Lynk service image builds."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT_INPUTS = {".dockerignore"}
SERVICE_DIRS = ("services/url-service/", "services/redirect-service/", "services/auth-service/")
SHARED_DIR = "packages/shared/"


def is_image_input(path: str) -> bool:
    """Return whether a changed path can affect one of the three images."""
    if path in ROOT_INPUTS or path.startswith(SHARED_DIR):
        return True
    if path.startswith(SERVICE_DIRS):
        return True
    return bool(re.fullmatch(r"(?:package.*|tsconfig.*)\.json", path))


def changed_paths(base: str, head: str) -> list[str]:
    """List additions, edits and deletions; disable rename collapsing."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", "--no-renames", base, head],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [part.decode("utf-8", errors="surrogateescape") for part in result.stdout.split(b"\0") if part]


def classify(paths: list[str], *, base_available: bool = True) -> dict[str, object]:
    """Any uncertain or relevant diff requests all three images."""
    matching = sorted(path for path in paths if is_image_input(path))
    build_images = not base_available or bool(matching)
    return {
        "build_images": build_images,
        "reason": "base-unavailable" if not base_available else ("image-input-changed" if matching else "no-image-input-changed"),
        "matching_paths": matching,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{40}", args.head):
        parser.error("head must be a full lowercase commit SHA")

    unavailable = (
        not re.fullmatch(r"[0-9a-f]{40}", args.base)
        or set(args.base) == {"0"}
        or subprocess.run(
            ["git", "cat-file", "-e", f"{args.base}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        != 0
    )
    try:
        paths = [] if unavailable else changed_paths(args.base, args.head)
        result = classify(paths, base_available=not unavailable)
    except (OSError, subprocess.CalledProcessError) as exc:
        # A failed diff must never suppress a needed image build.
        result = classify([], base_available=False)
        result["reason"] = f"diff-unavailable:{type(exc).__name__}"

    print(json.dumps(result, sort_keys=True))
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as output:
            output.write(f"build_images={'true' if result['build_images'] else 'false'}\n")
            output.write(f"reason={result['reason']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
