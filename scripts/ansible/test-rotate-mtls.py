#!/usr/bin/env python3
"""Test guarded mTLS controller phases with generated, disposable certificate fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


controller = load('rotate_controller', Path(__file__).with_name('rotate-mtls.py'))
pki = load('test_pki_generator', ROOT / 'scripts/secrets/prepare-mtls-pki.py')
bundle_module = load('test_bundle_contract', ROOT / 'scripts/secrets/vault-bundle.py')
vault = os.environ.get('LYNK_TEST_ANSIBLE_VAULT', 'ansible-vault')


@unittest.skipUnless(shutil.which(vault), 'ansible-vault is required')
class RotationControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lynk-rotation-test-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir(mode=0o700)
        generated = self.root / 'pki'
        pki.create(generated)
        previous = self.root / 'previous-pki'
        pki.create(previous)
        for name in bundle_module.NAMES:
            path = self.source / name
            if name in ('ca.crt','server.crt','server.key','client.crt','client.key'):
                shutil.copyfile(generated / name, path)
            else:
                path.write_bytes(('synthetic-' + name).encode())
            path.chmod(0o600)
        self.password = self.root / 'password'
        self.password.write_text('synthetic-controller-password\n')
        self.password.chmod(0o600)
        self.bundle = self.root / 'bundle.vault'
        subprocess.run([sys.executable, str(ROOT / 'scripts/secrets/vault-bundle.py'), 'pack',
                        '--source-dir', str(self.source), '--password-file', str(self.password),
                        '--ansible-vault', vault, '--output', str(self.bundle)],
                       check=True, capture_output=True, env={**os.environ, 'ANSIBLE_LOCAL_TEMP': str(self.root / 'ansible-tmp')})
        self.overlap = self.root / 'overlap.pem'
        self.overlap.write_bytes((previous / 'ca.crt').read_bytes() + (generated / 'ca.crt').read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def call(self, inventory_result=None, wrong_password=False, overlap=None):
        calls=[]
        directories=[]
        real_temp=controller.tempfile.TemporaryDirectory
        class RecordedTemp:
            def __init__(self, *args, **kwargs): self.inner=real_temp(*args, **kwargs)
            def __enter__(self):
                value=self.inner.__enter__(); directories.append(Path(value)); return value
            def __exit__(self,*args): return self.inner.__exit__(*args)
        original=controller.tempfile.TemporaryDirectory
        controller.tempfile.TemporaryDirectory=RecordedTemp
        def runner(command, **kwargs):
            calls.append(command)
            if '--list' in command:
                return inventory_result or SimpleNamespace(returncode=0,stdout='{"all":{"hosts":["lynk"]}}')
            if 'vault-bundle.py' in ' '.join(command):
                if wrong_password:
                    return SimpleNamespace(returncode=1)
                return subprocess.run(command, **kwargs)
            return SimpleNamespace(returncode=0)
        try:
            password=self.password
            if wrong_password:
                password=self.root/'wrong'; password.write_text('wrong\n'); password.chmod(0o600)
            try:
                result=controller.run_phase('stage', self.bundle, password, overlap or self.overlap,
                                             executable='/pinned/ansible-playbook', vault=vault, runner=runner)
                return result,calls,directories,None
            except Exception as error:
                return None,calls,directories,error
        finally:
            controller.tempfile.TemporaryDirectory=original

    def test_inventory_gate_stops_before_decryption(self):
        _result,calls,_directories,error=self.call(SimpleNamespace(returncode=1,stdout=''))
        self.assertIsInstance(error,RuntimeError)
        self.assertEqual(len(calls),1)
        self.assertIn('--list',calls[0])

    def test_valid_stage_passes_only_file_paths_and_cleans_plaintext(self):
        result,calls,directories,error=self.call()
        self.assertIsNone(error)
        self.assertEqual(result,0)
        self.assertTrue(any('rotate-mtls.yml' in ' '.join(call) for call in calls))
        self.assertTrue(all(not directory.exists() for directory in directories))
        self.assertNotIn('synthetic-controller-password',' '.join(map(str,calls)))

    def test_wrong_password_and_untrusted_overlap_stop_before_playbook(self):
        one_ca=self.root/'one-ca.pem'
        one_ca.write_bytes((self.source/'ca.crt').read_bytes())
        for wrong_password, overlap in ((True,None),(False,one_ca)):
            result,calls,directories,error=self.call(wrong_password=wrong_password,overlap=overlap)
            self.assertIsNotNone(error)
            self.assertFalse(any('rotate-mtls.yml' in ' '.join(call) for call in calls))
            self.assertTrue(all(not directory.exists() for directory in directories))


if __name__ == '__main__':
    unittest.main()
