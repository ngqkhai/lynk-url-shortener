#!/usr/bin/env python3
"""Exercise the actual workflow job conditions across events and delivery modes."""
import ast
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
DEPLOY = yaml.safe_load((ROOT / '.github/workflows/deploy-aws.yml').read_text())


def enabled(condition, mode, event, ref):
    # These guards use only equality comparisons, boolean operators and strings.
    # Restrict evaluation so a changed guard cannot execute Python code in CI.
    substitutions = {'github.ref': ref, 'github.event_name': event,
                     'needs.deployment-policy.outputs.mode': mode}
    expression = condition.replace('&&', 'and').replace('||', 'or')
    for key, value in substitutions.items():
        expression = expression.replace(key, repr(value))
    tree = ast.parse(expression, mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.Constant)
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise ValueError('Unsupported workflow condition: ' + condition)
    return eval(compile(tree, '<workflow condition>', 'eval'), {'__builtins__': {}})


class WorkflowGateTests(unittest.TestCase):
    def test_ci_and_manual_legacy_deploy_matrix(self):
        for workflow in (CI, DEPLOY):
            condition = workflow['jobs']['deploy']['if']
            for mode in ('paused', 'argocd', '', 'invalid', 'ssm'):
                for event in ('push', 'pull_request', 'workflow_dispatch'):
                    for ref in ('refs/heads/main', 'refs/heads/checkpoint/cp02-freeze-legacy'):
                        with self.subTest(workflow=workflow['name'], mode=mode, event=event, ref=ref):
                            expected = mode == 'ssm' and ref == 'refs/heads/main'
                            if workflow is CI:
                                expected = expected and event == 'push'
                            else:
                                expected = expected and event in ('push', 'workflow_dispatch')
                            self.assertEqual(enabled(condition, mode, event, ref), expected)

    def test_checks_do_not_depend_on_delivery_or_publication(self):
        for job in ('lint-and-test', 'gateway-e2e', 'automation-checks', 'gitops-checks'):
            config = CI['jobs'][job]
            self.assertNotIn('if', config)
            self.assertNotIn('needs', config)
        self.assertNotIn('needs', CI['jobs']['image-inputs'])

    def test_image_publication_depends_on_source_paths_and_all_quality_jobs(self):
        detection = CI['jobs']['image-inputs']
        publisher = CI['jobs']['build-and-push']
        self.assertEqual(detection['outputs']['build_images'], '${{ steps.classify.outputs.build_images }}')
        self.assertEqual(detection['steps'][0]['with']['fetch-depth'], 0)
        for job in ('lint-and-test', 'gateway-e2e', 'automation-checks', 'gitops-checks', 'terraform-checks', 'image-inputs'):
            self.assertIn(job, publisher['needs'])
        self.assertIn("github.ref == 'refs/heads/main'", publisher['if'])
        self.assertIn("github.event_name == 'push'", publisher['if'])
        self.assertIn("needs.image-inputs.outputs.build_images == 'true'", publisher['if'])

        package = CI['jobs']['package-release']
        self.assertEqual(package['needs'], 'build-and-push')
        self.assertIn('package-release', CI['jobs']['deploy']['needs'])
        build_step = next(step for step in publisher['steps'] if step.get('uses', '').startswith('docker/build-push-action@'))
        self.assertIn('${{ github.sha }}', build_step['with']['tags'])
        digest_step = next(step for step in publisher['steps'] if step.get('name') == 'Record digest')
        self.assertEqual(digest_step['env']['DIGEST'], '${{ steps.image.outputs.digest }}')

    def test_manual_and_reusable_deploy_cannot_skip_policy(self):
        self.assertIn('deployment-policy', CI['jobs']['deploy']['needs'])
        self.assertEqual(DEPLOY['jobs']['deploy']['needs'], 'deployment-policy')
        steps = DEPLOY['jobs']['deploy']['steps']
        guard = next(i for i, step in enumerate(steps)
                     if step.get('run') == 'python3 scripts/cd/deployment-mode.py --require-ssm')
        credentials = next(i for i, step in enumerate(steps)
                           if step.get('uses', '').startswith('aws-actions/configure-aws-credentials@'))
        self.assertLess(guard, credentials)
        self.assertEqual(DEPLOY['jobs']['deploy']['environment'], 'aws-demo')

    def test_node_workflows_keep_shared_non_canceling_concurrency(self):
        bootstrap = yaml.safe_load((ROOT / '.github/workflows/bootstrap-aws.yml').read_text())
        for workflow in (DEPLOY, bootstrap):
            self.assertEqual(workflow['concurrency'],
                             {'group': 'lynk-aws-deployment', 'cancel-in-progress': False})

    def test_argocd_promotion_is_guarded_serialized_and_scoped(self):
        promotion = CI['jobs']['promote-release']
        self.assertEqual(promotion['needs'], ['package-release', 'deployment-policy'])
        self.assertIn("needs.deployment-policy.outputs.mode == 'argocd'", promotion['if'])
        self.assertEqual(promotion['concurrency'], {
            'group': 'lynk-argocd-promotion', 'queue': 'max', 'cancel-in-progress': False
        })
        self.assertEqual(promotion['permissions'], {'contents': 'write', 'id-token': 'write'})
        self.assertEqual(promotion['environment'], 'aws-demo')
        self.assertIn('promotion_guard.py', '\n'.join(step.get('run', '') for step in promotion['steps']))
        self.assertIn('wait-argocd-status.py', '\n'.join(step.get('run', '') for step in promotion['steps']))
        rollback = next(step for step in promotion['steps'] if 'Restore desired values' in step.get('name', ''))
        self.assertIn('git revert --no-edit', rollback['run'])
        self.assertIn('git push origin HEAD:aws-demo', rollback['run'])
        self.assertNotIn('--force', rollback['run'])
        promotion_run = next(step['run'] for step in promotion['steps'] if step.get('id') == 'promotion')
        self.assertIn('git push origin HEAD:aws-demo', promotion_run)
        self.assertIn('git worktree add --detach /tmp/lynk-aws-demo origin/aws-demo', promotion_run)
        self.assertIn('--chart-sha', promotion_run)
        self.assertNotIn('git push origin HEAD:main', promotion_run)


if __name__ == '__main__':
    unittest.main()
