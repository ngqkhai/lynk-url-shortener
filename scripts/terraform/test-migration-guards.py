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
    def resize_fixture(self):
        return {"resource_changes": [{"address": "aws_instance.node", "change": {
            "actions": ["update"],
            "before": {"instance_type": "t3.small", "public_ip": "192.0.2.1", "root_block_device": [{"volume_size": 30}], "user_data_replace_on_change": None},
            "after": {"instance_type": "t3.medium", "public_ip": None, "root_block_device": [{"volume_size": 30}], "user_data_replace_on_change": False},
            "after_unknown": {"public_ip": True},
        }}]}

    def test_resize_accepts_only_type_with_narrow_provider_normalization(self):
        result = guards.check_resize_plan(self.resize_fixture(), "t3.small", "t3.medium")
        self.assertEqual(result["computed_unknowns"], ["public_ip"])
        self.assertTrue(result["provider_default_normalization"])

    def test_resize_rejects_disk_userdata_replacement_and_address_changes(self):
        for mutation in ["disk", "userdata", "replace", "address"]:
            plan = self.resize_fixture()
            change = plan["resource_changes"][0]["change"]
            if mutation == "disk":
                change["after"]["root_block_device"][0]["volume_size"] = 60
            elif mutation == "userdata":
                change["after"]["user_data_replace_on_change"] = True
            elif mutation == "replace":
                change["actions"] = ["delete", "create"]
            else:
                change["after"]["public_ip"] = "192.0.2.2"
                change["after_unknown"]["public_ip"] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                guards.check_resize_plan(plan, "t3.small", "t3.medium")

    def test_resize_rejects_other_resource_updates_and_larger_instances(self):
        plan = self.resize_fixture()
        plan["resource_changes"].append({"address": "aws_eip.node", "change": {"actions": ["update"]}})
        with self.assertRaises(ValueError):
            guards.check_resize_plan(plan, "t3.small", "t3.medium")
        with self.assertRaises(ValueError):
            guards.check_resize_plan(self.resize_fixture(), "t3.medium", "t3.large")

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
