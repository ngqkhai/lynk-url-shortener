#!/usr/bin/env python3
"""Exercise freshness and exact staged-path guards."""

import subprocess
import tempfile
import unittest
import os
from pathlib import Path

from promotion_guard import (
    ALLOWED_PATH,
    require_deployment_tree,
    require_fresh_source,
    require_only_values_path,
)

SHA = "a" * 40


class PromotionGuardTests(unittest.TestCase):
    def test_accepts_only_exact_source_tip(self):
        require_fresh_source(SHA, SHA)

    def test_rejects_stale_or_short_sha(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            require_fresh_source(SHA, "b" * 40)
        with self.assertRaisesRegex(ValueError, "full lowercase"):
            require_fresh_source("a" * 7, "a" * 40)

    def test_rejects_any_unapproved_staged_path(self):
        require_only_values_path([ALLOWED_PATH])
        with self.assertRaisesRegex(ValueError, "exactly"):
            require_only_values_path([ALLOWED_PATH, "README.md"])
        with self.assertRaisesRegex(ValueError, "exactly"):
            require_only_values_path([])

    def test_deployment_branch_may_change_only_values_from_chart_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            values = root / ALLOWED_PATH
            values.parent.mkdir(parents=True)
            values.write_text("baseline\n")
            (root / "chart.yaml").write_text("pinned\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-m", "chart"], check=True, capture_output=True)
            chart_sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            values.write_text("promoted\n")
            subprocess.run(["git", "-C", str(root), "commit", "-am", "promote"], check=True, capture_output=True)
            deployment_sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                require_deployment_tree(chart_sha, deployment_sha)
            finally:
                os.chdir(previous_cwd)
            (root / "chart.yaml").write_text("drift\n")
            subprocess.run(["git", "-C", str(root), "commit", "-am", "chart drift"], check=True, capture_output=True)
            drift_sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            os.chdir(root)
            try:
                with self.assertRaisesRegex(ValueError, "pinned chart"):
                    require_deployment_tree(chart_sha, drift_sha)
            finally:
                os.chdir(previous_cwd)

    def test_non_fast_forward_push_rejects_check_to_push_race(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bare = root / "remote.git"
            a = root / "a"
            b = root / "b"
            subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
            for path in (a, b):
                subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
                subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
                subprocess.run(["git", "-C", str(path), "remote", "add", "origin", str(bare)], check=True)
            (a / "state").write_text("base\n")
            subprocess.run(["git", "-C", str(a), "add", "state"], check=True)
            subprocess.run(["git", "-C", str(a), "commit", "-m", "base"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(a), "branch", "-M", "main"], check=True)
            subprocess.run(["git", "-C", str(a), "push", "-u", "origin", "main"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(b), "fetch", "origin", "main"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(b), "checkout", "-b", "main", "origin/main"], check=True, capture_output=True)
            (b / "state").write_text("remote advanced\n")
            subprocess.run(["git", "-C", str(b), "commit", "-am", "advance main"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(b), "push", "origin", "main"], check=True, capture_output=True)
            (a / "state").write_text("stale promotion\n")
            subprocess.run(["git", "-C", str(a), "commit", "-am", "promote stale release"], check=True, capture_output=True)
            push = subprocess.run(["git", "-C", str(a), "push", "origin", "main"], capture_output=True, text=True)
            self.assertNotEqual(push.returncode, 0)
            self.assertIn("rejected", push.stderr)


if __name__ == "__main__":
    unittest.main()
