#!/usr/bin/env python3
"""Keep the host status checker install and Application update narrowly scoped."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "infra/ansible"


def main():
    status = yaml.safe_load((ANSIBLE / "argocd-status.yml").read_text())[0]
    status_source = status["vars"]["status_script"].replace("{{ playbook_dir }}", str(ANSIBLE))
    status_dest = status["vars"]["installed_script"]
    copy_task = next(task for task in status["tasks"] if task["name"].startswith("Install the status checker"))
    args = copy_task["ansible.builtin.copy"]
    source = args["src"].replace("{{ status_script }}", status_source)
    assert Path(source).resolve() == (ROOT / "scripts/cd/argocd-status.sh").resolve()
    assert args["dest"] == "{{ installed_script }}" and status_dest == "/opt/lynk/bin/argocd-status.sh"
    assert args["owner"] == args["group"] == "root" and args["mode"] == "0700"

    app = yaml.safe_load((ANSIBLE / "argocd-application-sources.yml").read_text())[0]
    apply = next(task for task in app["tasks"] if task["name"].startswith("Apply only the Application"))
    argv = apply["ansible.builtin.command"]["argv"]
    assert argv == ["{{ kubectl }}", "apply", "--server-side", "-f", "{{ manifest_dir }}/aws-demo-application.yaml"]
    assert any("workload_snapshot_before.stdout == workload_snapshot_after.stdout" in str(task) for task in app["tasks"])
    print("PASS: status helper installs from repository root with mode 0700; live apply is limited to Application and checks workload snapshot equality")


if __name__ == "__main__":
    main()
