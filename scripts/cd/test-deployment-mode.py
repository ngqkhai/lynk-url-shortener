#!/usr/bin/env python3
"""Test fail-closed delivery configuration and the pre-credential guard."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('deployment-mode.py')


class DeploymentModeTests(unittest.TestCase):
    def run_mode(self, mode, require_ssm=False):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            env = {key: value for key, value in os.environ.items()
                   if key not in ('LYNK_DEPLOY_MODE', 'GITHUB_OUTPUT')}
            env['GITHUB_OUTPUT'] = str(output)
            if mode is not None:
                env['LYNK_DEPLOY_MODE'] = mode
            result = subprocess.run(
                [sys.executable, str(SCRIPT)] + (['--require-ssm'] if require_ssm else []),
                env=env, capture_output=True, text=True, check=False,
            )
            return result, output.read_text() if output.exists() else ''

    def test_missing_or_empty_configuration_pauses(self):
        for mode in (None, ''):
            with self.subTest(mode=mode):
                result, output = self.run_mode(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, 'mode=paused\n')

    def test_recognized_modes_emit_exactly_one_output(self):
        for mode in ('paused', 'ssm', 'argocd'):
            with self.subTest(mode=mode):
                result, output = self.run_mode(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, 'mode=' + mode + '\n')

    def test_invalid_or_injected_configuration_fails_without_output(self):
        for mode in ('SSM', 'true', ' ssm', 'ssm\nmode=ssm', '${{ secrets.TOKEN }}'):
            with self.subTest(mode=mode):
                result, output = self.run_mode(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')
                self.assertEqual(result.stderr,
                                 'Invalid LYNK_DEPLOY_MODE; expected paused, ssm or argocd\n')

    def test_precredential_guard_blocks_every_mode_except_ssm(self):
        for mode in (None, '', 'paused', 'argocd', 'invalid', 'ssm'):
            with self.subTest(mode=mode):
                result, output = self.run_mode(mode, require_ssm=True)
                if mode == 'ssm':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output, 'mode=ssm\n')
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(output, '')


if __name__ == '__main__':
    unittest.main()
