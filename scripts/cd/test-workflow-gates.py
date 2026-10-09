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
        self.assertNotIn('deployment-policy', CI['jobs']['build-and-push']['needs'])

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


if __name__ == '__main__':
    unittest.main()
