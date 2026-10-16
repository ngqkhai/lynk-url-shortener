#!/usr/bin/env python3
"""Test guards against destructive ownership-transfer plans with synthetic data."""

import copy
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("guards", Path(__file__).with_name("migration-guards.py"))
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)


class MigrationGuards(unittest.TestCase):
    def test_retention_preserves_intrinsics_properties_and_outputs(self):
        original = "Resources:\n  Node:\n    Type: AWS::EC2::Instance\n    Properties:\n      SubnetId: !Ref Subnet\nOutputs:\n  NodeId: {Value: !Ref Node}\n"
        candidate = guards.retain_template(original, ["Node"])
        self.assertEqual(
            candidate.replace("    DeletionPolicy: Retain\n", "").replace("    UpdateReplacePolicy: Retain\n", ""),
            original,
        )
        self.assertEqual(guards.retain_template(candidate, ["Node"]), candidate)

    def test_retention_rejects_inventory_mismatch_and_unexpected_policy(self):
        original = "Resources:\n  Node:\n    Type: AWS::EC2::Instance\n"
        with self.assertRaises(ValueError):
            guards.retain_template(original, ["OtherNode"])
        with self.assertRaises(ValueError):
            guards.retain_template(original + "    DeletionPolicy: Delete\n", ["Node"])

    def fixture(self):
        return (
            {"resource_changes": [{"address": "aws_instance.node", "change": {"actions": ["no-op"], "importing": {"id": "i-fixture"}}}]},
            {"resources": [{"address": "aws_instance.node", "import_id": "i-fixture"}]},
        )

    def test_exact_import_plan_passes(self):
        plan, mapping = self.fixture()
        self.assertEqual(guards.check_import_plan(plan, mapping)["imports"], 1)

    def test_import_rejects_create_update_delete_and_replacement(self):
        plan, mapping = self.fixture()
        for actions in [["create"], ["update"], ["delete"], ["delete", "create"]]:
            changed = copy.deepcopy(plan)
            changed["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                guards.check_import_plan(changed, mapping)

    def test_import_rejects_wrong_id_missing_import_or_extra_resource(self):
        plan, mapping = self.fixture()
        for mutation in ["wrong_id", "no_import", "extra", "wrong_address"]:
            changed = copy.deepcopy(plan)
            change = changed["resource_changes"][0]
            if mutation == "wrong_id":
                change["change"]["importing"]["id"] = "i-other"
            elif mutation == "no_import":
                del change["change"]["importing"]
            elif mutation == "extra":
                changed["resource_changes"].append(copy.deepcopy(change))
            else:
                change["address"] = "aws_instance.other"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                guards.check_import_plan(changed, mapping)


if __name__ == "__main__":
    unittest.main()
