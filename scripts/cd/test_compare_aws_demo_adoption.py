#!/usr/bin/env python3
"""Test the protected resource boundaries for an aws-demo adoption sync."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_aws_demo_adoption import EXPECTED_HOOK_JOBS, compare


def snapshot():
    return {
        "namespace": "lynk-aws",
        "deployments": [{"name": "url-service", "uid": "deployment-1", "replicas": 1, "containers": [["url", "image@sha256:abc", {}, {}]]}],
        "statefulsets": [{"name": "kafka", "uid": "kafka-1", "replicas": 1, "containers": [["kafka", "image@sha256:def", {}, {}]]}],
        "services": [{"name": "url-service", "uid": "service-1", "type": "ClusterIP", "clusterIP": "10.0.0.1", "selector": {"app": "url-service"}, "ports": [{"port": 3001}]}],
        "ingresses": [{"name": "lynk-public", "uid": "ingress-1", "rules": [{"host": "lynk.codes"}]}],
        "persistentvolumeclaims": [{"name": "data-kafka-0", "uid": "pvc-1", "phase": "Bound", "volumeName": "pv-1", "storageClassName": "local-path", "accessModes": ["ReadWriteOnce"]}],
        "pods": [{"name": "url-service-abc", "uid": "pod-1", "ownerReferences": [["ReplicaSet", "url-service-abc"]], "containers": [["url", "image@sha256:abc", True, 0]]}],
        "jobs": [{"name": "kafka-topics", "uid": "job-1"}],
    }


class AdoptionSnapshotTests(unittest.TestCase):
    def test_accepts_only_expected_hook_jobs_with_protected_resources_unchanged(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["jobs"].extend({"name": name, "uid": name + "-uid"} for name in EXPECTED_HOOK_JOBS)
        compare(before, after)

    def test_rejects_pvc_replacement(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["persistentvolumeclaims"][0]["uid"] = "different-pvc"
        after["jobs"].extend({"name": name, "uid": name + "-uid"} for name in EXPECTED_HOOK_JOBS)
        with self.assertRaisesRegex(ValueError, "persistentvolumeclaims"):
            compare(before, after)

    def test_rejects_pod_replacement(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["pods"][0]["uid"] = "different-pod"
        after["jobs"].extend({"name": name, "uid": name + "-uid"} for name in EXPECTED_HOOK_JOBS)
        with self.assertRaisesRegex(ValueError, "Pod identity"):
            compare(before, after)

    def test_rejects_unexpected_added_job(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["jobs"].extend({"name": name, "uid": name + "-uid"} for name in EXPECTED_HOOK_JOBS)
        after["jobs"].append({"name": "unexpected", "uid": "unexpected-uid"})
        with self.assertRaisesRegex(ValueError, "unexpected hook Job"):
            compare(before, after)

    def test_partial_sync_accepts_expected_presync_jobs_while_postsync_is_pending(self):
        before = snapshot()
        after = copy.deepcopy(before)
        presync = EXPECTED_HOOK_JOBS - {"lynk-postsync-smoke"}
        after["jobs"].extend({"name": name, "uid": name + "-uid"} for name in presync)
        compare(before, after, allow_pending_hooks=True)
        with self.assertRaisesRegex(ValueError, "unexpected hook Job"):
            compare(before, after)


if __name__ == "__main__":
    unittest.main()
