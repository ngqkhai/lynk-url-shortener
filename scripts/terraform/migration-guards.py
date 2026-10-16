#!/usr/bin/env python3
"""Prepare policy-only CF retention and reject AWS changes in import plans."""

import argparse
import json
import os
from pathlib import Path
import re


def retain_template(body, expected_names):
    """Preserve live YAML bytes except for adding missing Retain attributes."""
    lines = body.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip() == "Resources:"]
    if len(starts) != 1:
        raise ValueError("Expected one block-style top-level Resources section")
    start = starts[0] + 1
    end = next(
        (i for i in range(start, len(lines)) if re.match(r"^[A-Za-z][A-Za-z0-9]*:", lines[i])),
        len(lines),
    )
    resources = [
        (i, re.fullmatch(r"  ([A-Za-z0-9]+):\s*", lines[i]).group(1))
        for i in range(start, end)
        if re.fullmatch(r"  ([A-Za-z0-9]+):\s*", lines[i])
    ]
    if len(resources) != len(expected_names) or {name for _, name in resources} != set(expected_names):
        raise ValueError("Template logical IDs differ from live inventory")
    insertions = {}
    for index, (position, name) in enumerate(resources):
        boundary = resources[index + 1][0] if index + 1 < len(resources) else end
        block = "".join(lines[position + 1:boundary])
        if not re.search(r"^    Type: ", block, re.M):
            raise ValueError("Expected an explicit Type for " + name)
        missing = []
        for attribute in ["DeletionPolicy", "UpdateReplacePolicy"]:
            values = re.findall(r"^    " + attribute + r":\s*([^\n]+)$", block, re.M)
            if len(values) > 1 or any(value.strip() != "Retain" for value in values):
                raise ValueError("Unexpected existing retention policy for " + name)
            if not values:
                missing.append("    " + attribute + ": Retain\n")
        insertions[position] = "".join(missing)
    candidate = "".join(line + insertions.get(i, "") for i, line in enumerate(lines))
    # All original bytes remain in their original order; only policy lines added.
    return candidate


def check_import_plan(plan, mapping):
    entries = mapping["resources"]
    expected = {entry["address"]: entry["import_id"] for entry in entries}
    changes = plan.get("resource_changes", [])
    if len(expected) != len(entries) or len(changes) != len(expected):
        raise ValueError("Duplicate mapping or unexpected resource count")
    if {change["address"] for change in changes} != set(expected):
        raise ValueError("Plan resource addresses differ from reviewed mapping")
    for resource in changes:
        change = resource["change"]
        if change["actions"] != ["no-op"]:
            raise ValueError("Import plan would change AWS: " + resource["address"])
        if change.get("importing", {}).get("id") != expected[resource["address"]]:
            raise ValueError("Missing or incorrect import ID: " + resource["address"])
    return {"imports": len(expected), "creates": 0, "updates": 0, "deletes": 0}


def check_resize_plan(plan, source_type, target_type):
    if {source_type, target_type} != {"t3.small", "t3.medium"}:
        raise ValueError("Only the agreed small/medium resize or its recovery is allowed")
    resources = plan.get("resource_changes", [])
    if any(resource["change"].get("importing") for resource in resources):
        raise ValueError("Resize must not import additional bindings")
    changes = [resource for resource in resources if resource["change"]["actions"] != ["no-op"]]
    if len(changes) != 1 or changes[0]["address"] != "aws_instance.node":
        raise ValueError("Resize must change only the existing node")
    change = changes[0]["change"]
    if change["actions"] != ["update"] or change.get("replace_paths"):
        raise ValueError("Resize must not create, destroy or replace resources")
    before, after = change["before"], change["after"]
    if before["instance_type"] != source_type or after["instance_type"] != target_type:
        raise ValueError("Unexpected instance types")
    differences = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    if not differences <= {"instance_type", "public_ip", "public_dns", "user_data_replace_on_change"}:
        raise ValueError("Resize includes unrelated attribute changes")
    computed = sorted(differences & {"public_ip", "public_dns"})
    for key in computed:
        if change.get("after_unknown", {}).get(key) is not True:
            raise ValueError("Public address fields may only become computed unknowns")
    normalized = "user_data_replace_on_change" in differences
    if normalized and not (
        before.get("user_data_replace_on_change") is None
        and after.get("user_data_replace_on_change") is False
    ):
        raise ValueError("Unexpected UserData lifecycle policy change")
    return {
        "updates": 1, "creates": 0, "deletes": 0, "replacement": False,
        "from_type": source_type, "to_type": target_type,
        "configured_change": "instance_type",
        "computed_unknowns": computed,
        "provider_default_normalization": normalized,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    retain = commands.add_parser("retain")
    retain.add_argument("--template-response", required=True)
    retain.add_argument("--inventory", required=True)
    retain.add_argument("--stack", required=True)
    retain.add_argument("--output", required=True)
    check = commands.add_parser("check-import-plan")
    check.add_argument("--plan", required=True)
    check.add_argument("--mapping", required=True)
    resize = commands.add_parser("check-resize-plan")
    resize.add_argument("--plan", required=True)
    resize.add_argument("--from-type", required=True)
    resize.add_argument("--to-type", required=True)
    args = parser.parse_args()
    if args.command == "retain":
        body = json.loads(Path(args.template_response).read_text())["TemplateBody"]
        inventory = json.loads(Path(args.inventory).read_text())[args.stack]
        names = [resource["LogicalResourceId"] for resource in inventory]
        if not isinstance(body, str):
            parser.error("Expected the live original YAML template as a string")
        candidate = retain_template(body, names)
        os.umask(0o077)
        with Path(args.output).open("x") as output:
            output.write(candidate)
        print(json.dumps({"stack": args.stack, "resources": len(names), "policy_only": True}))
    elif args.command == "check-import-plan":
        print(json.dumps(check_import_plan(
            json.loads(Path(args.plan).read_text()),
            json.loads(Path(args.mapping).read_text()),
        )))
    else:
        print(json.dumps(check_resize_plan(
            json.loads(Path(args.plan).read_text()), args.from_type, args.to_type,
        )))


if __name__ == "__main__":
    main()
