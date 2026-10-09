#!/usr/bin/env python3
"""Run as root on the node; emit only CMS-encrypted runtime files and safe metadata."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile

NAMES = ('auth.env', 'url.env', 'redirect.env', 'redis-password',
         'jwt-private.pem', 'jwt-public.pem', 'ca.crt', 'server.crt',
         'server.key', 'client.crt', 'client.key')
REFERENCES = {
    'auth.env': ('auth-service-db', 'DATABASE_URL'),
    'url.env': ('url-service-db', 'DATABASE_URL'),
    'redirect.env': ('redirect-service-db', 'DATABASE_URL'),
    'redis-password': ('lynk-redis-auth', 'redis-password'),
    'jwt-private.pem': ('lynk-jwt-keys', 'jwt-private.pem'),
    'jwt-public.pem': ('lynk-jwt-keys', 'jwt-public.pem'),
    'ca.crt': ('lynk-gateway-ca', 'ca.crt'),
    'server.crt': ('lynk-gateway-server', 'server.crt'),
    'server.key': ('lynk-gateway-server', 'server.key'),
    'client.crt': ('lynk-gateway-client', 'tls.crt'),
    'client.key': ('lynk-gateway-client', 'tls.key'),
}


def capture(recipient):
    if os.geteuid() != 0:
        raise ValueError('Root required')
    root = Path('/opt/lynk/secrets')
    directory = root.lstat()
    if not stat.S_ISDIR(directory.st_mode) or stat.S_IMODE(directory.st_mode) != 0o700 or directory.st_uid != 0:
        raise ValueError('Unexpected directory permissions')
    env = {**os.environ, 'KUBECONFIG': '/etc/rancher/k3s/k3s.yaml'}
    secrets = json.loads(subprocess.run(
        ['kubectl', '-n', 'lynk-aws', 'get', 'secrets',
         *sorted({name for name, key in REFERENCES.values()}), '-o', 'json'],
        env=env, check=True, capture_output=True, timeout=30,
    ).stdout)
    secrets = {item['metadata']['name']: item['data'] for item in secrets['items']}
    files = {}
    file_uids = {}
    for name in NAMES:
        path = root / name
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError('Unexpected file type')
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError('Unexpected file permissions')
        data = path.read_bytes()
        if not data or len(data) > 65536:
            raise ValueError('Unexpected file size')
        value = data
        if name.endswith('.env'):
            lines = [line.split(b'=', 1)[1] for line in data.splitlines()
                     if line.startswith(b'DATABASE_URL=')]
            if len(lines) != 1:
                raise ValueError('Missing database configuration')
            value = lines[0]
        secret, key = REFERENCES[name]
        if value != base64.b64decode(secrets[secret][key], validate=True):
            raise ValueError('Runtime file does not match Kubernetes Secret')
        files[name] = data
        file_uids[name] = metadata.st_uid
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode='w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    with tempfile.TemporaryDirectory(prefix='lynk-vault-recipient-') as directory:
        certificate = Path(directory) / 'recipient.pem'
        certificate.write_text(recipient)
        encrypted = subprocess.run(
            ['openssl', 'cms', '-encrypt', '-binary', '-outform', 'DER',
             '-aes-256-cbc', '-recip', str(certificate),
             '-keyopt', 'rsa_padding_mode:oaep'],
            input=bundle.getvalue(), capture_output=True, check=True, timeout=30,
        ).stdout
    result = json.dumps({
        'version': 1, 'files': list(NAMES), 'runtime_matches': True,
        'directory_mode': '0700', 'file_mode': '0600',
        'file_uids': file_uids,
        'ca_key_present_at_expected_path': (root / 'ca.key').exists(),
        'encrypted_bundle': base64.b64encode(encrypted).decode('ascii'),
    })
    if len(result.encode()) >= 23000:
        raise ValueError('Encrypted response exceeds bounded SSM output size')
    print(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipient-pem', required=True)
    args = parser.parse_args()
    try:
        capture(args.recipient_pem)
    except Exception:
        # Do not expose subprocess output, parsed credentials or exception values.
        print('Runtime secret capture failed; no plaintext output emitted', file=sys.stderr)
        raise SystemExit(1)
