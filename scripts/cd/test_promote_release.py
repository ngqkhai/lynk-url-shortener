#!/usr/bin/env python3
"""Test release validation and the narrowly scoped values promotion."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from promote_release import promoted_values, validate_release


SHA = "a" * 40
RELEASE = {
    "version": 1,
    "commit": SHA,
    "images": {
        service: {
            "image": {
                "repository": f"ghcr.io/ngqkhai/lynk-{service.removesuffix('Service')}-service",
                "digest": "sha256:" + digest * 64,
            }
        }
        for service, digest in (("urlService", "1"), ("redirectService", "2"), ("authService", "3"))
    },
}
VALUES = {
    "global": {"imageTag": "b" * 40, "migrationHookMode": "argocd", "postSyncSmoke": {"enabled": True}},
    "urlService": {"image": {"repository": "ghcr.io/ngqkhai/lynk-url-service", "digest": "sha256:" + "a" * 64, "pullPolicy": "IfNotPresent"}},
    "redirectService": {"image": {"repository": "ghcr.io/ngqkhai/lynk-redirect-service", "digest": "sha256:" + "a" * 64, "pullPolicy": "IfNotPresent"}},
    "authService": {"image": {"repository": "ghcr.io/ngqkhai/lynk-auth-service", "digest": "sha256:" + "a" * 64, "pullPolicy": "IfNotPresent"}},
}


class PromoteReleaseTests(unittest.TestCase):
    def test_promotes_exact_three_digests_and_preserves_other_values(self):
        original = copy.deepcopy(VALUES)
        result = promoted_values(copy.deepcopy(VALUES), RELEASE, SHA)
        self.assertEqual(result["global"]["imageTag"], SHA)
        self.assertEqual(result["global"]["migrationHookMode"], "argocd")
        self.assertEqual(result["global"]["postSyncSmoke"], {"enabled": True})
        self.assertEqual(result["urlService"]["image"]["digest"], RELEASE["images"]["urlService"]["image"]["digest"])
        self.assertEqual(result["redirectService"]["image"]["digest"], RELEASE["images"]["redirectService"]["image"]["digest"])
        self.assertEqual(result["authService"]["image"]["digest"], RELEASE["images"]["authService"]["image"]["digest"])
        for service in ("urlService", "redirectService", "authService"):
            self.assertEqual(result[service]["image"]["pullPolicy"], original[service]["image"]["pullPolicy"])

    def test_refuses_mismatched_or_malformed_release(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_release({**RELEASE, "commit": "c" * 40}, SHA)
        bad = copy.deepcopy(RELEASE)
        bad["images"]["urlService"]["image"]["digest"] = "latest"
        with self.assertRaisesRegex(ValueError, "invalid repository or digest"):
            validate_release(bad, SHA)

    def test_refuses_unexpected_repositories_and_incomplete_image_sets(self):
        values = copy.deepcopy(VALUES)
        values["authService"]["image"]["repository"] = "example.invalid/other"
        with self.assertRaisesRegex(ValueError, "unexpected repository"):
            promoted_values(values, RELEASE, SHA)
        bad = copy.deepcopy(RELEASE)
        del bad["images"]["authService"]
        with self.assertRaisesRegex(ValueError, "exactly the three"):
            validate_release(bad, SHA)

    def test_promotes_allowlisted_values_from_a_separate_git_worktree(self):
        script = Path(__file__).with_name("promote_release.py").resolve()
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            values_path = repository / "infra/k8s/helm/lynk-services/values-aws-demo.yaml"
            values_path.parent.mkdir(parents=True)
            values_path.write_text(yaml.safe_dump(VALUES, sort_keys=False), encoding="utf-8")
            release_path = repository / "release.json"
            release_path.write_text(json.dumps(RELEASE), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repository-root",
                    str(repository),
                    "--release-json",
                    str(release_path),
                    "--values",
                    "infra/k8s/helm/lynk-services/values-aws-demo.yaml",
                    "--expected-sha",
                    SHA,
                ],
                cwd=repository,
                capture_output=True,
                check=True,
                text=True,
            )

            promoted = yaml.safe_load(values_path.read_text(encoding="utf-8"))
            self.assertEqual(promoted["global"]["imageTag"], SHA)
            self.assertEqual(promoted["urlService"]["image"]["digest"], RELEASE["images"]["urlService"]["image"]["digest"])
            self.assertIn(SHA, result.stdout)

    def test_worktree_root_still_rejects_a_non_allowlisted_values_path(self):
        script = Path(__file__).with_name("promote_release.py").resolve()
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            values_path = repository / "values.yaml"
            values_path.write_text("{}\n", encoding="utf-8")
            release_path = repository / "release.json"
            release_path.write_text(json.dumps(RELEASE), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repository-root",
                    str(repository),
                    "--release-json",
                    str(release_path),
                    "--values",
                    "values.yaml",
                    "--expected-sha",
                    SHA,
                ],
                cwd=repository,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("values path must be exactly", result.stderr)


if __name__ == "__main__":
    unittest.main()
