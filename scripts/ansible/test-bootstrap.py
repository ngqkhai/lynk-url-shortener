#!/usr/bin/env python3
"""Exercise metadata disclosure and controller cleanup with synthetic fixtures."""

import copy
import importlib.util
import json
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory = load("inventory", ROOT / "infra/ansible/inventory.py")
controller = load("controller", Path(__file__).with_name("bootstrap.py"))


class BootstrapTests(unittest.TestCase):
    def outputs(self):
        return {name: {"type": "string", "sensitive": False, "value": value} for name, value in {
            "instance_id": "i-0123456789abcdef0",
            "artifact_bucket": "lynk-k3s-dev-artifactbucket-fixture",
            "database_backup_bucket": "lynk-db-backups-231136241975-ap-southeast-1",
            "region": "ap-southeast-1",
        }.items()}

    def test_inventory_exports_only_required_metadata(self):
        outputs = self.outputs()
        outputs["database_url"] = {"sensitive": True, "value": "fixture-secret"}
        result = inventory.inventory_from_outputs(outputs)
        self.assertEqual(result["_meta"]["hostvars"]["lynk"]["ansible_host"], "i-0123456789abcdef0")
        self.assertNotIn("fixture-secret", json.dumps(result))

    def test_inventory_rejects_wrong_identity_region_bucket_and_sensitive_contract(self):
        for field, value in [("instance_id", "127.0.0.1"), ("region", "us-east-1"), ("artifact_bucket", "other-account-bucket"), ("database_backup_bucket", "wrong-bucket")]:
            changed = self.outputs()
            changed[field]["value"] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                inventory.inventory_from_outputs(changed)
        changed = copy.deepcopy(self.outputs())
        changed["instance_id"]["sensitive"] = True
        with self.assertRaises(ValueError):
            inventory.inventory_from_outputs(changed)

    def test_controller_cleans_plaintext_after_success_and_unreachable(self):
        for returncode in [0, 2]:
            seen = {}
            def runner(command, **kwargs):
                if "--list" in command:
                    return SimpleNamespace(returncode=0, stdout='{"all":{"hosts":["lynk"]}}')
                if "restore" in command:
                    path = Path(command[command.index("--output-dir") + 1])
                    seen["directory"] = path.parent
                    self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
                    path.mkdir(mode=0o700)
                    (path / "fixture").write_text("synthetic-plaintext")
                    return SimpleNamespace(returncode=0)
                variables = Path(command[command.index("--extra-vars") + 1][1:])
                self.assertEqual(stat.S_IMODE(variables.stat().st_mode), 0o600)
                self.assertNotIn("synthetic-plaintext", " ".join(command))
                return SimpleNamespace(returncode=returncode)
            self.assertEqual(controller.run_bootstrap(["--password-env", "FIXTURE_PASSWORD"], runner=runner), returncode)
            self.assertFalse(seen["directory"].exists())

    def test_controller_cleans_when_ansible_cannot_start(self):
        seen = {}
        def runner(command, **kwargs):
            if "--list" in command:
                return SimpleNamespace(returncode=0, stdout='{"all":{"hosts":["lynk"]}}')
            if "restore" in command:
                path = Path(command[command.index("--output-dir") + 1]);seen["directory"] = path.parent
                path.mkdir(mode=0o700)
                return SimpleNamespace(returncode=0)
            raise OSError("synthetic child startup failure")
        with self.assertRaises(OSError):
            controller.run_bootstrap(["--password-env", "FIXTURE_PASSWORD"], runner=runner)
        self.assertFalse(seen["directory"].exists())

    def test_controller_does_not_run_ansible_after_failed_decryption(self):
        seen = {}
        def runner(command, **kwargs):
            if "--list" in command:
                return SimpleNamespace(returncode=0, stdout='{"all":{"hosts":["lynk"]}}')
            self.assertIn("restore", command)
            seen["directory"] = Path(command[command.index("--output-dir") + 1]).parent
            return SimpleNamespace(returncode=1)
        with self.assertRaises(RuntimeError):
            controller.run_bootstrap(["--password-env", "FIXTURE_PASSWORD"], runner=runner)
        self.assertFalse(seen["directory"].exists())

    def test_controller_fails_before_decrypt_when_inventory_is_unavailable(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=1, stdout="", stderr="credentials unavailable")
        with self.assertRaisesRegex(RuntimeError, "inventory"):
            controller.run_bootstrap(["--password-env", "FIXTURE_PASSWORD"], runner=runner)
        self.assertEqual(len(calls), 1)
        self.assertIn("--list", calls[0])

    def test_controller_fails_before_decrypt_when_inventory_has_no_hosts(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout='{"all":{"hosts":[]}}')
        with self.assertRaisesRegex(RuntimeError, "exactly the Lynk host"):
            controller.run_bootstrap(["--password-env", "FIXTURE_PASSWORD"], runner=runner)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
