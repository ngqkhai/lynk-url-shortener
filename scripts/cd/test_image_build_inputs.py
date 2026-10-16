#!/usr/bin/env python3
"""Test the image input boundary and its relationship to Dockerfiles."""

import re
import unittest
from unittest.mock import patch
from pathlib import Path

from image_build_inputs import changed_paths, classify, is_image_input


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("url", "redirect", "auth")


class ImageBuildInputTests(unittest.TestCase):
    def test_every_docker_copy_source_is_covered(self):
        for service in SERVICES:
            dockerfile = ROOT / "services" / f"{service}-service" / "Dockerfile"
            for line in dockerfile.read_text().splitlines():
                if not line.startswith("COPY "):
                    continue
                fields = line.split()
                if fields[1].startswith("--from="):
                    continue
                for source in fields[1:-1]:
                    path = source.removeprefix("./")
                    if path.startswith("/"):
                        continue
                    if path.endswith("/"):
                        path = path.rstrip("/") + "/probe"
                    self.assertTrue(is_image_input(path), f"unclassified Docker COPY source: {source} in {dockerfile}")

    def test_service_changes_trigger_image_build(self):
        for path in (
            "services/url-service/src/server.ts",
            "services/redirect-service/drizzle/0001.sql",
            "services/auth-service/Dockerfile",
        ):
            with self.subTest(path=path):
                self.assertTrue(classify([path])["build_images"])

    def test_shared_and_root_dependency_changes_trigger_all_images(self):
        for path in (
            "packages/shared/src/index.ts",
            "packages/shared/package.json",
            "package.json",
            "package-lock.json",
            "tsconfig.json",
            ".dockerignore",
            ".github/workflows/ci.yml",
        ):
            with self.subTest(path=path):
                self.assertTrue(classify([path])["build_images"])

    def test_gitops_infrastructure_and_documentation_do_not_trigger_images(self):
        for path in (
            "gitops/aws-demo-application.yaml",
            "infra/terraform/environments/aws-demo/main.tf",
            "infra/k8s/helm/lynk-services/values-aws-demo.yaml",
            "docs/runbook/deployment-checkpoints/cp14-ci-dependency-graph.md",
            "scripts/cd/image_build_inputs.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(classify([path])["build_images"])

    def test_deletion_and_multiple_commit_path_lists_are_classified(self):
        result = classify(["gitops/old-app.yaml", "services/url-service/drizzle/old.sql"])
        self.assertTrue(result["build_images"])
        self.assertEqual(result["matching_paths"], ["services/url-service/drizzle/old.sql"])

    def test_missing_base_is_fail_safe(self):
        self.assertTrue(classify([], base_available=False)["build_images"])

    def test_git_diff_keeps_deleted_paths_and_does_not_collapse_renames(self):
        completed = type("Completed", (), {"stdout": b"gitops/old.yaml\0services/url-service/old.sql\0"})()
        with patch("image_build_inputs.subprocess.run", return_value=completed) as run:
            self.assertEqual(
                changed_paths("a" * 40, "b" * 40),
                ["gitops/old.yaml", "services/url-service/old.sql"],
            )
        self.assertIn("--no-renames", run.call_args.args[0])
        self.assertIn("-z", run.call_args.args[0])

    def test_dockerfile_copy_sources_use_supported_patterns(self):
        for service in SERVICES:
            content = (ROOT / "services" / f"{service}-service" / "Dockerfile").read_text()
            self.assertRegex(content, re.compile(r"COPY package\*\.json tsconfig\*\.json"))


if __name__ == "__main__":
    unittest.main()
