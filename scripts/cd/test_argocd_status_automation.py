#!/usr/bin/env python3
"""Keep the host status checker install and Application update narrowly scoped."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "infra/ansible"


def main():
    status_checker = (ROOT / "scripts/cd/argocd-status.sh").read_text()
    assert 'kubectl logs "deployment/$name" -n lynk-aws --tail=100' in status_checker
    assert "record.get('releaseSha') == expected" in status_checker
    assert 'check_deployment url-service "$url_digest" "$release_sha"' in status_checker
    assert "--ignore-not-found" in status_checker
    assert "operation history does not record a successful PostSync smoke hook" in status_checker
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    build = next(step for step in workflow["jobs"]["build-and-push"]["steps"] if step.get("id") == "image")
    assert build["with"]["build-args"] == "RELEASE_SHA=${{ github.sha }}"
    for service in ("url", "redirect", "auth"):
        dockerfile = (ROOT / f"services/{service}-service/Dockerfile").read_text()
        assert "ARG RELEASE_SHA=local" in dockerfile and "RELEASE_SHA=${RELEASE_SHA}" in dockerfile

    status = yaml.safe_load((ANSIBLE / "argocd-status.yml").read_text())[0]
    status_source = status["vars"]["status_script"].replace("{{ playbook_dir }}", str(ANSIBLE))
    status_dest = status["vars"]["installed_script"]
    copy_task = next(task for task in status["tasks"] if task["name"].startswith("Install the status checker"))
    args = copy_task["ansible.builtin.copy"]
    source = args["src"].replace("{{ status_script }}", status_source)
    assert Path(source).resolve() == (ROOT / "scripts/cd/argocd-status.sh").resolve()
    assert args["dest"] == "{{ installed_script }}" and status_dest == "/opt/lynk/bin/argocd-status.sh"
    assert args["owner"] == args["group"] == "root" and args["mode"] == "0700"

    app = yaml.safe_load((ANSIBLE / "argocd-application-aws-demo-branch.yml").read_text())[0]
    apply = next(task for task in app["tasks"] if task["name"].startswith("Patch only spec.source.targetRevision"))
    argv = apply["ansible.builtin.command"]["argv"]
    assert argv[:7] == ["{{ kubectl }}", "patch", "application", "aws-demo", "-n", "argocd", "--type=json"]
    assert "/spec/source/targetRevision" in app["vars"]["source_patch"]
    dry_run = next(task for task in app["tasks"] if task["name"].startswith("Server-side dry-run"))
    assert "--dry-run=server" in dry_run["ansible.builtin.command"]["argv"]
    assert any("snapshot_before.stdout == snapshot_after.stdout" in str(task) for task in app["tasks"])
    assert any("'aws-demo'" in str(task) for task in app["tasks"])

    recovery = yaml.safe_load((ANSIBLE / "restore-aws-demo-single-source.yml").read_text())[0]
    patch = recovery["vars"]["restore_patch"]
    assert '"/spec/sources"' in patch and '"/spec/source"' in patch
    assert "87eb22600c545ac6952d472739b0091f5bd84281" in patch
    assert any("--dry-run=server" in str(task) for task in recovery["tasks"])
    assert any("recovery_snapshot_before.stdout == recovery_snapshot_after.stdout" in str(task) for task in recovery["tasks"])
    print("PASS: status helper installs from repository root with mode 0700; Application update/recovery stay scoped to the CR and check workload snapshot equality")


if __name__ == "__main__":
    main()
