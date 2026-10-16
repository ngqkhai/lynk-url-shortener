#!/usr/bin/env python3
"""Exercise convergence, release identity and strict deadlines without a cluster."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('checker', Path(__file__).with_name('argocd-status.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REVISION, SHA = 'a' * 40, 'b' * 40
DIGESTS = {name + '-service': 'sha256:' + digit * 64 for name, digit in (('url', '1'), ('redirect', '2'), ('auth', '3'))}


def application():
    return {'status': {'sync': {'revision': REVISION, 'status': 'Synced'}, 'health': {'status': 'Healthy'},
                       'operationState': {'phase': 'Succeeded', 'syncResult': {'revision': REVISION, 'resources': [
                           {'name': 'lynk-postsync-smoke', 'namespace': 'lynk-aws', 'kind': 'Job', 'hookType': 'PostSync',
                            'hookPhase': 'Succeeded', 'images': ['registry/url@' + DIGESTS['url-service']]}
                       ]}}}}


class Clock:
    now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Cluster:
    def __init__(self):
        self.apps = [application()]
        self.calls = 0
        self.pod_digest = None
        self.deployment_digest = None
        self.logs_sha = SHA
        self.job = None
        self.padding = ''

    def run(self, *args):
        if args[:2] == ('get', 'application'):
            app = self.apps[min(self.calls, len(self.apps) - 1)]
            self.calls += 1
            return json.dumps(app)
        if args[:2] == ('get', 'deployment'):
            name = args[2]
            return json.dumps({'metadata': {'generation': 1, 'padding': self.padding},
                               'spec': {'replicas': 1, 'template': {'spec': {'containers': [
                                   {'name': name, 'image': 'registry/test@' + (self.deployment_digest or DIGESTS[name])}]}}},
                               'status': {'readyReplicas': 1, 'observedGeneration': 1}})
        if args[:2] == ('get', 'pods'):
            name = args[args.index('-l') + 1].removeprefix('app=')
            smoke = name == 'lynk-postsync-smoke'
            digest = DIGESTS['url-service'] if smoke else self.pod_digest or DIGESTS[name]
            return json.dumps({'items': [{'metadata': {'name': name + '-pod'}, 'status': {
                'phase': 'Succeeded' if smoke else 'Running', 'containerStatuses': [
                    {'name': 'smoke' if smoke else name, 'ready': True, 'imageID': 'registry/test@' + digest}]}}]})
        if args[0] == 'logs':
            return json.dumps({'releaseSha': self.logs_sha, 'padding': self.padding})
        if args[:2] == ('get', 'job'):
            return json.dumps(self.job) if self.job is not None else ''
        raise AssertionError('unexpected command: ' + repr(args))


class ReleaseStatusTests(unittest.TestCase):
    def check(self, cluster):
        return MODULE.check_once(cluster.run, REVISION, SHA, DIGESTS)

    def test_waits_for_revision_and_operation_then_accepts_exact_release(self):
        cluster, clock = Cluster(), Clock()
        old, syncing = application(), application()
        old['status']['sync']['revision'] = 'c' * 40
        old['status']['operationState']['syncResult']['revision'] = 'c' * 40
        syncing['status']['operationState']['phase'] = 'Running'
        cluster.apps = [old, syncing, application()]
        result = MODULE.wait_for_release(lambda: self.check(cluster), 60, clock.monotonic, clock.sleep, lambda _: None)
        self.assertEqual(result, {'values_revision': REVISION, 'release_sha': SHA, 'status': 'Healthy', 'smoke': 'Succeeded'})
        self.assertEqual(clock.now, 20)

    def test_never_converging_release_reaches_deadline(self):
        clock = Clock()
        def pending():
            raise MODULE.Pending('not yet')
        with self.assertRaises(TimeoutError):
            MODULE.wait_for_release(pending, 23, clock.monotonic, clock.sleep, lambda _: None)
        self.assertEqual(clock.now, 23)

    def test_terminal_failure_does_not_retry(self):
        clock = Clock()
        def failed():
            raise MODULE.Terminal('access denied')
        with self.assertRaises(MODULE.Terminal):
            MODULE.wait_for_release(failed, 840, clock.monotonic, clock.sleep)
        self.assertEqual(clock.now, 0)

    def test_failed_operation_or_hook_is_terminal_for_requested_revision(self):
        for hook in (False, True):
            cluster = Cluster()
            if hook:
                cluster.apps[0]['status']['operationState']['syncResult']['resources'][0]['hookPhase'] = 'Failed'
            else:
                cluster.apps[0]['status']['operationState']['phase'] = 'Failed'
            with self.subTest(hook=hook), self.assertRaises(MODULE.Terminal):
                self.check(cluster)

    def test_wrong_revision_digest_or_release_log_is_not_success(self):
        for field in ('revision', 'deployment_digest', 'pod_digest', 'logs_sha'):
            cluster = Cluster()
            if field == 'revision':
                cluster.apps[0]['status']['sync']['revision'] = 'c' * 40
            else:
                setattr(cluster, field, 'sha256:' + 'f' * 64 if 'digest' in field else 'c' * 40)
            with self.subTest(field=field), self.assertRaises(MODULE.Pending):
                self.check(cluster)

    def test_expired_job_requires_exact_hook_history(self):
        self.assertEqual(self.check(Cluster())['smoke'], 'Succeeded')
        for field, value in (('hookPhase', 'Running'), ('images', ['registry/wrong@sha256:' + 'f' * 64]),
                             ('namespace', 'other')):
            cluster = Cluster()
            cluster.apps[0]['status']['operationState']['syncResult']['resources'][0][field] = value
            with self.subTest(field=field), self.assertRaises(MODULE.Pending):
                self.check(cluster)
        cluster = Cluster()
        cluster.apps[0]['status']['operationState']['syncResult']['revision'] = 'c' * 40
        with self.assertRaises(MODULE.Pending):
            self.check(cluster)

    def test_existing_smoke_job_checks_runtime_image_and_failure(self):
        cluster = Cluster()
        cluster.job = {'spec': {'template': {'spec': {'containers': [{'image': 'registry/url@' + DIGESTS['url-service']}]}}},
                       'status': {'succeeded': 1}}
        self.assertEqual(self.check(cluster)['smoke'], 'Succeeded')
        cluster.job['status'] = {'conditions': [{'type': 'Failed', 'status': 'True'}]}
        with self.assertRaises(MODULE.Terminal):
            self.check(cluster)

    def test_large_objects_and_logs_do_not_use_command_arguments(self):
        cluster = Cluster()
        cluster.padding = 'x' * 300000
        self.assertEqual(self.check(cluster)['status'], 'Healthy')

    def test_inflight_kubectl_timeout_is_bounded_by_remaining_global_deadline(self):
        clock = Clock()
        clock.now = 838
        run = MODULE.kubectl_runner(840, clock.monotonic)
        with patch.object(MODULE.subprocess, 'run', side_effect=subprocess.TimeoutExpired('kubectl', 2)) as command:
            with self.assertRaises(MODULE.Pending):
                run('get', 'application')
            self.assertEqual(command.call_args.kwargs['timeout'], 2)
        clock.now = 840
        with self.assertRaises(TimeoutError):
            run('get', 'application')

    def test_permission_errors_and_malformed_payloads_are_terminal(self):
        with patch.object(MODULE.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'Forbidden')):
            with self.assertRaises(MODULE.Terminal):
                MODULE.kubectl_runner(840, lambda: 0)('get', 'application')
        with self.assertRaises(MODULE.Terminal):
            MODULE.check_once(lambda *_: 'not-json', REVISION, SHA, DIGESTS)

    def test_invalid_cli_arguments_exit_before_accessing_kubernetes(self):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('argocd-status.py')),
                                 'invalid', SHA, *DIGESTS.values()], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid revision', result.stderr)


if __name__ == '__main__':
    unittest.main()
