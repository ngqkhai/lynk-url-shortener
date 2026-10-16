#!/usr/bin/env python3
"""Verify service ownership, S3 integrity gates, and success-only retention with fixtures."""
import base64
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('lynk-db-backup.py')
SPEC = importlib.util.spec_from_file_location('lynk_db_backup', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@contextmanager
def fixture_snapshot(*_args):
    yield '00000001-00000001-1', {'urls': 3}, {'p': 1, 'u': 1}


def completed(command, stdout=b'{}', code=0):
    return SimpleNamespace(args=command, stdout=stdout, stderr=b'', returncode=code)


class FakeS3Runner:
    def __init__(self, fail_archive_head=False, existing_manifests=None):
        self.objects = {}
        self.calls = []
        self.fail_archive_head = fail_archive_head
        self.existing_manifests = existing_manifests or []

    def __call__(self, command, **_kwargs):
        self.calls.append(command)
        if command[0].endswith('kubectl'):
            connection = 'postgresql://lynk_url:synthetic-password@ep-sample.c-4.ap-southeast-1.aws.neon.tech/lynk_urls?sslmode=require'
            value = {'data': {'DATABASE_URL': base64.b64encode(connection.encode()).decode()}}
            return completed(command, json.dumps(value).encode())
        if command[0].endswith('pg_dump') and '--version' in command:
            return completed(command, b'pg_dump (PostgreSQL) 18.6')
        if command[0].endswith('pg_dump'):
            archive = Path(command[command.index('--file') + 1])
            archive.write_bytes(b'SYNTHETIC-CUSTOM-ARCHIVE')
            return completed(command, b'')
        if command[0].endswith('pg_restore'):
            return completed(command, b'TABLE public urls\n')
        if command[0].endswith('aws'):
            operation = command[command.index('s3api') + 1]
            key = command[command.index('--key') + 1] if '--key' in command else None
            if operation == 'put-object':
                path = Path(command[command.index('--body') + 1])
                data = path.read_bytes()
                digest = base64.b64encode(hashlib.sha256(data).digest()).decode()
                expected = command[command.index('--checksum-sha256') + 1]
                if digest != expected:
                    return completed(command, b'', 1)
                self.objects[key] = {'body': data, 'checksum': digest, 'size': len(data)}
                return completed(command)
            if operation == 'head-object':
                if self.fail_archive_head and key.endswith('.dump'):
                    return completed(command, b'', 1)
                item = self.objects[key]
                return completed(command, json.dumps({'ServerSideEncryption': 'AES256', 'ChecksumSHA256': item['checksum'], 'ContentLength': item['size']}).encode())
            if operation == 'list-objects-v2':
                contents = [{'Key': key} for key in self.objects]
                contents += [{'Key': key} for key in self.existing_manifests]
                return completed(command, json.dumps({'Contents': contents}).encode())
            if operation == 'delete-object':
                self.objects.pop(key, None)
                return completed(command)
        raise AssertionError('Unexpected command category: ' + command[0])


class DatabaseBackupTests(unittest.TestCase):
    def secret(self, url):
        return {'data': {'DATABASE_URL': base64.b64encode(url.encode()).decode()}}

    def test_database_url_is_direct_and_owned_by_the_selected_service(self):
        url = 'postgresql://lynk_url:fixture%3Apassword@ep-direct.c-4.ap-southeast-1.aws.neon.tech/lynk_urls?sslmode=require'
        environment = MODULE.database_environment(self.secret(url), 'url')
        self.assertEqual(environment['PGDATABASE'], 'lynk_urls')
        self.assertEqual(environment['PGUSER'], 'lynk_url')
        self.assertEqual(environment['PGPASSWORD'], 'fixture:password')
        self.assertEqual(environment['PGSSLMODE'], 'verify-full')
        for invalid in (
            url.replace('/lynk_urls', '/lynk_redirects'),
            url.replace('lynk_url:', 'neondb_owner:'),
            url.replace('ep-direct.', 'ep-direct-pooler.'),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                MODULE.database_environment(self.secret(invalid), 'url')
        self.assertNotIn('fixture:password', environment['PGHOST'] + environment['PGUSER'] + environment['PGDATABASE'])

    def test_success_writes_manifest_after_verified_archive_and_prunes_afterwards(self):
        snapshot_active = {'value': False}

        @contextmanager
        def held_snapshot(*_args):
            snapshot_active['value'] = True
            try:
                yield '00000001-00000001-1', {'urls': 3}, {'p': 1, 'u': 1}
            finally:
                snapshot_active['value'] = False

        class SnapshotAwareRunner(FakeS3Runner):
            def __call__(self, command, **kwargs):
                if command[0].endswith('pg_dump') and not snapshot_active['value']:
                    raise AssertionError('exported snapshot transaction must remain open during pg_dump')
                return super().__call__(command, **kwargs)

        runner = SnapshotAwareRunner()
        with patch.object(MODULE, 'exported_snapshot', held_snapshot):
            result = MODULE.backup_service('url', 'test-bucket', runner=runner)
        manifest_key = result['manifest_key']
        self.assertTrue(manifest_key.endswith('.manifest.json'))
        self.assertIn(manifest_key.removesuffix('.manifest.json') + '.dump', runner.objects)
        manifest = json.loads(runner.objects[manifest_key]['body'])
        self.assertEqual(manifest['row_counts'], {'urls': 3})
        self.assertEqual(manifest['role'], 'lynk_url')
        operations = [call[call.index('s3api') + 1] for call in runner.calls if 's3api' in call]
        self.assertEqual(operations[:4], ['put-object', 'head-object', 'put-object', 'head-object'])
        self.assertEqual(operations[4], 'list-objects-v2')

    def test_failed_archive_verification_never_writes_manifest_or_prunes(self):
        runner = FakeS3Runner(fail_archive_head=True)
        with patch.object(MODULE, 'exported_snapshot', fixture_snapshot):
            with self.assertRaisesRegex(MODULE.BackupFailure, 'archive_upload_or_integrity_check'):
                MODULE.backup_service('url', 'test-bucket', runner=runner)
        operations = [call[call.index('s3api') + 1] for call in runner.calls if 's3api' in call]
        self.assertEqual(operations, ['put-object', 'head-object'])

    def test_retention_deletes_old_manifest_before_its_archive_only_after_success(self):
        prefix = 'db-backups/lynk_urls/'
        keys = [prefix + f'2026100{i}T020000Z-x.manifest.json' for i in range(1, 9)]
        runner = FakeS3Runner(existing_manifests=keys)
        retained = MODULE.prune_after_success('test-bucket', prefix, runner=runner)
        self.assertEqual(retained, 7)
        deleted = [call[call.index('--key') + 1] for call in runner.calls if 'delete-object' in call]
        self.assertEqual(deleted, [keys[0], keys[0].removesuffix('.manifest.json') + '.dump'])


if __name__ == '__main__':
    unittest.main()
