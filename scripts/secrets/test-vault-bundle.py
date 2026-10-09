#!/usr/bin/env python3
"""Verify restoration and failure handling using synthetic Vault fixtures only."""
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('vault-bundle.py')
SPEC = importlib.util.spec_from_file_location('vault_bundle', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
VAULT = os.environ.get('LYNK_TEST_ANSIBLE_VAULT', 'ansible-vault')


class VaultBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which(VAULT) is None:
            raise RuntimeError('ansible-vault is required for synthetic recovery tests')
        cls.tmp = tempfile.TemporaryDirectory(prefix='lynk-vault-test-')
        cls.root = Path(cls.tmp.name)
        cls.old_local_temp = os.environ.get('ANSIBLE_LOCAL_TEMP')
        os.environ['ANSIBLE_LOCAL_TEMP'] = str(cls.root / 'ansible-tmp')
        cls.password = cls.root / 'password'
        cls.password.touch(mode=0o600)
        cls.password.write_text('synthetic-test-password-only\n')
        cls.data = b'SYNTHETIC_FILE_CONTENT_NOT_A_RUNTIME_SECRET'
        cls.good = cls.make_bundle('good', [(name, cls.data) for name in MODULE.NAMES])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        if cls.old_local_temp is None:
            os.environ.pop('ANSIBLE_LOCAL_TEMP', None)
        else:
            os.environ['ANSIBLE_LOCAL_TEMP'] = cls.old_local_temp

    @classmethod
    def make_bundle(cls, label, entries):
        plain = cls.root / (label + '.tar.gz')
        plain.touch(mode=0o600)
        with tarfile.open(plain, 'w:gz') as archive:
            for name, data in entries:
                member = tarfile.TarInfo(name)
                member.mode = 0o600
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        encrypted = cls.root / (label + '.vault')
        subprocess.run([VAULT, 'encrypt', '--vault-id', 'aws-demo@' + str(cls.password),
                        '--output', str(encrypted), str(plain)],
                       check=True, capture_output=True)
        plain.unlink()
        return encrypted

    def run_bundle(self, action, bundle=None, password=None, output=None):
        command = [sys.executable, str(SCRIPT), action, '--bundle', str(bundle or self.good),
                   '--ansible-vault', VAULT, '--password-file', str(password or self.password)]
        if output is not None:
            command += ['--output-dir', str(output)]
        scratch = self.root / ('scratch-' + self._testMethodName)
        scratch.mkdir(mode=0o700, exist_ok=True)
        result = subprocess.run(command, env={**os.environ, 'TMPDIR': str(scratch)},
                                capture_output=True, text=True)
        self.assertEqual(list(scratch.iterdir()), [], 'Temporary decrypted data must be cleaned')
        self.assertNotIn(self.data.decode(), result.stdout + result.stderr)
        return result

    def test_verify_roundtrip_and_cleanup(self):
        result = self.run_bundle('verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('temporary plaintext cleaned', result.stdout)

    def test_restore_bytes_permissions_and_refuse_existing_destination(self):
        output = self.root / 'restored'
        result = self.run_bundle('restore', output=output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        for name in MODULE.NAMES:
            self.assertEqual((output / name).read_bytes(), self.data)
            self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)
        (output / MODULE.NAMES[0]).write_bytes(b'KEEP_EXISTING_KEY')
        self.assertNotEqual(self.run_bundle('restore', output=output).returncode, 0)
        self.assertEqual((output / MODULE.NAMES[0]).read_bytes(), b'KEEP_EXISTING_KEY')
        shutil.rmtree(output)

    def test_wrong_password_and_ciphertext_tampering_fail_without_plaintext(self):
        password = self.root / 'wrong-password'
        password.touch(mode=0o600)
        password.write_text('different-synthetic-test-password\n')
        self.assertNotEqual(self.run_bundle('verify', password=password).returncode, 0)
        tampered = self.root / 'tampered.vault'
        data = bytearray(self.good.read_bytes())
        # Last hex digit still forms valid framing, but authentication must fail.
        index = len(data.rstrip()) - 1
        data[index] = ord('0') if data[index] != ord('0') else ord('1')
        tampered.write_bytes(data)
        self.assertNotEqual(self.run_bundle('verify', bundle=tampered).returncode, 0)

    def test_missing_or_traversing_or_duplicate_members_fail_before_extraction(self):
        entries = [(name, self.data) for name in MODULE.NAMES]
        cases = {'missing': entries[:-1], 'traversal': entries + [('../escape', self.data)],
                 'duplicate': entries + [entries[0]]}
        for label, members in cases.items():
            with self.subTest(label=label):
                bundle = self.make_bundle(label, members)
                output = self.root / ('reject-' + label)
                self.assertNotEqual(self.run_bundle('restore', bundle=bundle, output=output).returncode, 0)
                self.assertFalse(output.exists())
        self.assertFalse((self.root / 'escape').exists())

    def test_symlink_member_is_rejected(self):
        plain = io.BytesIO()
        with tarfile.open(fileobj=plain, mode='w:gz') as archive:
            member = tarfile.TarInfo(MODULE.NAMES[0])
            member.type = tarfile.SYMTYPE
            member.linkname = '/etc/passwd'
            archive.addfile(member)
        output = self.root / 'reject-link'
        with self.assertRaises(ValueError):
            MODULE.unpack(plain.getvalue(), output)
        self.assertFalse(output.exists())

    def test_ciphertext_check_needs_no_key_and_rejects_plaintext(self):
        result = self.run_bundle('check')
        self.assertEqual(result.returncode, 0, result.stderr)
        plain = self.root / 'not-encrypted.vault'
        plain.write_bytes(self.data)
        self.assertNotEqual(self.run_bundle('check', bundle=plain).returncode, 0)

    def test_password_environment_and_unsafe_password_permissions(self):
        scratch = self.root / 'env-scratch'
        scratch.mkdir(mode=0o700)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), 'verify', '--bundle', str(self.good),
             '--ansible-vault', VAULT, '--password-env', 'TEST_VAULT_PASSWORD'],
            env={**os.environ, 'TMPDIR': str(scratch),
                 'TEST_VAULT_PASSWORD': self.password.read_text().strip()},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(scratch.iterdir()), [])
        unsafe = self.root / 'unsafe-password'
        unsafe.write_text(self.password.read_text())
        unsafe.chmod(0o644)
        self.assertNotEqual(self.run_bundle('verify', password=unsafe).returncode, 0)


if __name__ == '__main__':
    unittest.main()
