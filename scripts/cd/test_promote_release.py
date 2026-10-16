#!/usr/bin/env python3
"""Test release validation and the narrowly scoped values promotion."""

import copy
import unittest

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


if __name__ == "__main__":
    unittest.main()
