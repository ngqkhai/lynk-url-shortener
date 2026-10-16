#!/usr/bin/env python3
"""Exercise mTLS PKI preparation using ephemeral synthetic keys only."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('prepare-mtls-pki.py')
SPEC = importlib.util.spec_from_file_location('prepare_mtls_pki', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@unittest.skipUnless(shutil.which('openssl'), 'OpenSSL is required')
class MtlsPkiTests(unittest.TestCase):
    def test_generated_identity_contract_and_reject_existing_directory(self):
        with tempfile.TemporaryDirectory(prefix='lynk-pki-test-') as directory:
            root = Path(directory) / 'pki'
            sizes = MODULE.create(root)
            self.assertEqual(set(sizes), {'ca.crt', 'ca-signing.key', 'server.crt', 'server.key', 'client.crt', 'client.key'})
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            for name in ('ca-signing.key', 'server.key', 'client.key'):
                self.assertEqual((root / name).stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                MODULE.create(root)

    def test_wrong_hostname_and_wrong_tls_purpose_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='lynk-pki-negative-') as directory:
            root = Path(directory) / 'pki'
            MODULE.create(root)
            for arguments in (
                ['-purpose', 'sslserver', '-verify_hostname', 'wrong.example', str(root / 'server.crt')],
                ['-purpose', 'sslclient', str(root / 'server.crt')],
                ['-purpose', 'sslserver', str(root / 'client.crt')],
            ):
                import subprocess
                result = subprocess.run(['openssl', 'verify', '-CAfile', str(root / 'ca.crt'), *arguments], capture_output=True)
                self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
