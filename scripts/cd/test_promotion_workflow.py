#!/usr/bin/env python3
"""Execute the shipped workflow shell against real, isolated local Git remotes."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml
from test_promote_release import RELEASE, VALUES

ROOT = Path(__file__).resolve().parents[2]
STEPS = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']['promote-release']['steps']
PROMOTION = next(step['run'] for step in STEPS if step.get('id') == 'promotion')
RECOVERY = next(step['run'] for step in STEPS if step.get('name', '').startswith('Restore desired values'))
ALLOWED = 'infra/k8s/helm/lynk-services/values-aws-demo.yaml'
REAL_GIT = shutil.which('git')


class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lynk-workflow-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source checkout'
        self.remote = self.root / 'remote.git'
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
        for key in ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL'):
            self.env.pop(key, None)
        self.git(self.root, 'init', '--bare', str(self.remote))
        self.git(self.root, 'init', '-b', 'main', str(self.source))
        self.git(self.source, 'remote', 'add', 'origin', str(self.remote))
        path = self.source / ALLOWED
        path.parent.mkdir(parents=True)
        path.write_text(yaml.safe_dump(VALUES, sort_keys=False))
        self.git(self.source, 'add', '.')
        self.commit(self.source, 'chart baseline')
        self.chart = self.git(self.source, 'rev-parse', 'HEAD')
        self.git(self.source, 'push', 'origin', 'HEAD:aws-demo')
        scripts = self.source / 'scripts/cd'
        scripts.mkdir(parents=True)
        for name in ('promotion_guard.py', 'promote_release.py'):
            shutil.copyfile(ROOT / 'scripts/cd' / name, scripts / name)
        self.git(self.source, 'add', '.')
        self.commit(self.source, 'source tooling')
        self.sha = self.git(self.source, 'rev-parse', 'HEAD')
        self.git(self.source, 'push', 'origin', 'main')
        release = copy.deepcopy(RELEASE)
        release['commit'] = self.sha
        artifact = self.source / 'release-artifact/extracted/release.json'
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps(release))
        self.runner = self.root / 'runner temp'
        self.runner.mkdir()
        self.env.update(GITHUB_WORKSPACE=str(self.source), RUNNER_TEMP=str(self.runner), SOURCE_SHA=self.sha,
                        CHART_SHA=self.chart, GITHUB_OUTPUT=str(self.root / 'outputs'))

    def git(self, cwd, *args):
        return subprocess.run([REAL_GIT, '-C', str(cwd), *args], env=self.env,
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, cwd, message):
        self.git(cwd, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-am', message)

    def head(self, branch):
        return self.git(self.remote, 'rev-parse', 'refs/heads/' + branch)

    def run_step(self, script):
        return subprocess.run(['bash', '-e', '-c', script], cwd=self.source, env=self.env,
                              capture_output=True, text=True, timeout=20)

    def promote(self):
        result = self.run_step(PROMOTION)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.head('aws-demo')

    def recovery(self, sha):
        self.env['PROMOTION_SHA'] = sha
        return self.run_step(RECOVERY)

    def race(self, mode):
        parent = self.sha if mode == 'main' else self.chart
        tree = self.git(self.source, 'rev-parse', parent + '^{tree}')
        advance = self.git(self.source, '-c', 'user.name=Racer', '-c', 'user.email=racer@example.invalid',
                           'commit-tree', tree, '-p', parent, '-m', 'concurrent advancement')
        self.git(self.source, 'push', 'origin', advance + ':refs/heads/race-seed')
        self.env.update(RACE_MODE=mode, RACE_SHA=advance, RACE_REMOTE=str(self.remote),
                        RACE_COUNT=str(self.root / 'count'), REAL_GIT=REAL_GIT)
        wrapper = self.root / 'bin'
        wrapper.mkdir()
        shim = wrapper / 'git'
        shim.write_text('''#!/usr/bin/env python3
import os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]; real = os.environ['REAL_GIT']; mode = os.environ['RACE_MODE']
if args == ['fetch', 'origin', 'main'] and mode == 'main':
    counter = Path(os.environ['RACE_COUNT']); count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    if count == 2:
        subprocess.run([real, '-C', os.environ['RACE_REMOTE'], 'update-ref', 'refs/heads/main', os.environ['RACE_SHA']], check=True)
if args == ['push', 'origin', 'HEAD:aws-demo'] and mode == 'aws-demo':
    subprocess.run([real, '-C', os.environ['RACE_REMOTE'], 'update-ref', 'refs/heads/aws-demo', os.environ['RACE_SHA']], check=True)
if args[:2] == ['add', '--'] and mode == 'staged':
    Path('unapproved.txt').write_text('must not be promoted')
    subprocess.run([real, 'add', 'unapproved.txt'], check=True)
os.execv(real, [real, *args])
''')
        shim.chmod(0o755)
        self.env['PATH'] = str(wrapper) + os.pathsep + self.env['PATH']
        return advance

    def test_success_uses_source_scripts_and_changes_only_allowlisted_file(self):
        promoted = self.promote()
        self.assertEqual(self.head('main'), self.sha)
        self.assertEqual(self.git(self.remote, 'diff', '--name-only', self.chart, promoted), ALLOWED)
        values = yaml.safe_load(self.git(self.remote, 'show', promoted + ':' + ALLOWED))
        self.assertEqual(values['global']['imageTag'], self.sha)
        for service in RELEASE['images']:
            self.assertEqual(values[service]['image']['digest'], RELEASE['images'][service]['image']['digest'])
        self.assertIn('promotion_created=true', (self.root / 'outputs').read_text())
        self.assertFalse((self.runner / 'lynk-aws-demo/scripts').exists())

    def test_noop_does_not_commit_or_push(self):
        promoted = self.promote()
        self.git(self.source, 'worktree', 'remove', str(self.runner / 'lynk-aws-demo'))
        (self.root / 'outputs').unlink()
        self.assertEqual(self.promote(), promoted)
        self.assertIn('promotion_created=false', (self.root / 'outputs').read_text())

    def test_stale_source_is_rejected_before_worktree_creation(self):
        self.env['SOURCE_SHA'] = 'f' * 40
        result = self.run_step(PROMOTION)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stale', result.stderr)
        self.assertEqual(self.head('aws-demo'), self.chart)

    def test_source_advancing_before_final_check_is_rejected(self):
        self.race('main')
        result = self.run_step(PROMOTION)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stale', result.stderr)
        self.assertEqual(self.head('aws-demo'), self.chart)

    def test_non_fast_forward_race_is_rejected(self):
        advance = self.race('aws-demo')
        result = self.run_step(PROMOTION)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('rejected', result.stderr)
        self.assertEqual(self.head('aws-demo'), advance)

    def test_unapproved_staged_file_is_rejected(self):
        self.race('staged')
        result = self.run_step(PROMOTION)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exactly', result.stderr)
        self.assertEqual(self.head('aws-demo'), self.chart)

    def test_recovery_works_without_global_or_local_git_identity(self):
        promoted = self.promote()
        result = self.recovery(promoted)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('deployment verification remains failed', result.stderr)
        self.assertEqual(self.git(self.remote, 'diff', self.chart, self.head('aws-demo')), '')
        self.assertEqual(self.head('main'), self.sha)

    def test_recovery_refuses_when_either_remote_head_advanced(self):
        promoted = self.promote()
        for branch, parent in (('main', self.sha), ('aws-demo', promoted)):
            with self.subTest(branch=branch):
                tree = self.git(self.source, 'rev-parse', parent + '^{tree}')
                advance = self.git(self.source, '-c', 'user.name=Racer', '-c', 'user.email=racer@example.invalid',
                                   'commit-tree', tree, '-p', parent, '-m', 'concurrent advancement')
                self.git(self.source, 'push', 'origin', advance + ':refs/heads/race-' + branch)
                self.git(self.remote, 'update-ref', 'refs/heads/' + branch, advance)
                result = self.recovery(promoted)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Cannot safely revert', result.stderr)
                self.git(self.remote, 'update-ref', 'refs/heads/' + branch,
                         self.sha if branch == 'main' else promoted)
                self.git(self.source, 'worktree', 'remove', str(self.runner / 'lynk-aws-demo-rollback'))


if __name__ == '__main__':
    unittest.main()
