#!/usr/bin/env python3
"""Check Vault ciphertext or restore its fixed runtime-file contract locally."""
import argparse
import io
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

NAMES = ('auth.env', 'url.env', 'redirect.env', 'redis-password',
         'jwt-private.pem', 'jwt-public.pem', 'ca.crt', 'server.crt',
         'server.key', 'client.crt', 'client.key')
DEFAULT_BUNDLE = Path(__file__).resolve().parents[2] / 'infra/ansible/vault/aws-demo.tar.gz.vault'


def check_ciphertext(path):
    data = path.read_bytes()
    if len(data) > 1048576:
        raise ValueError('Vault bundle exceeds size limit')
    lines = data.splitlines()
    if len(lines) < 2 or lines[0] != b'$ANSIBLE_VAULT;1.2;AES256;aws-demo':
        raise ValueError('Expected aws-demo Vault envelope')
    if any(not re.fullmatch(rb'[0-9a-f]{1,80}', line) for line in lines[1:]):
        raise ValueError('Invalid ciphertext body')
    body = bytes.fromhex(b''.join(lines[1:]).decode('ascii')).split(b'\n')
    if len(body) != 3 or any(not re.fullmatch(rb'[0-9a-f]+', part) for part in body):
        raise ValueError('Invalid Vault payload framing')
    if len(body[0]) != 64 or len(body[1]) != 64 or len(body[2]) % 32:
        raise ValueError('Invalid Vault salt/HMAC/ciphertext lengths')


def unpack(data, destination):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive:
            if member.name not in NAMES or member.name in files or not member.isfile():
                raise ValueError('Unexpected archive member')
            if member.mode != 0o600 or not 0 < member.size <= 65536:
                raise ValueError('Unexpected archive permissions or size')
            files[member.name] = archive.extractfile(member).read()
    if set(files) != set(NAMES):
        raise ValueError('Incomplete runtime bundle')
    destination.mkdir(mode=0o700)  # Refuse an existing destination; never overwrite keys.
    try:
        for name in NAMES:
            descriptor = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(files[name])
    except Exception:
        shutil.rmtree(destination)
        raise


def decrypt(bundle, password_file, password_env, executable, directory):
    if password_env:
        password = os.environ.get(password_env)
        if not password:
            raise ValueError('Vault password environment variable is missing')
        password_file = directory / 'password'
        descriptor = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(password + '\n')
    elif not password_file or not password_file.is_file():
        raise ValueError('Explicit Vault password file is required')
    metadata = password_file.stat()
    if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid():
        raise ValueError('Vault password file must be owned by this user with mode 0600')
    output = directory / 'bundle.tar.gz'
    # Reserve the output with restrictive mode before the CLI writes plaintext.
    output.touch(mode=0o600)
    result = subprocess.run(
        [executable, 'decrypt', '--vault-id', 'aws-demo@' + str(password_file),
         '--output', str(output), str(bundle)], capture_output=True,
        env={**os.environ, 'ANSIBLE_LOCAL_TEMP': str(directory / 'ansible-tmp')},
    )
    if result.returncode != 0:
        raise ValueError('Vault decryption failed (details suppressed)')
    output.chmod(0o600)
    return output.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'verify', 'restore'))
    parser.add_argument('--bundle', type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument('--ansible-vault', default='ansible-vault')
    password = parser.add_mutually_exclusive_group()
    password.add_argument('--password-file', type=Path)
    password.add_argument('--password-env')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    try:
        check_ciphertext(args.bundle)
        if args.action == 'check':
            print('PASS: aws-demo Vault ciphertext framing (decryption not checked)')
            return 0
        if args.action == 'restore' and args.output_dir is None:
            raise ValueError('Restore requires an explicit output directory')
        if args.action == 'verify' and args.output_dir is not None:
            raise ValueError('Verify does not retain restored plaintext')
        with tempfile.TemporaryDirectory(prefix='lynk-vault-') as directory:
            root = Path(directory)
            data = decrypt(args.bundle, args.password_file, args.password_env,
                           args.ansible_vault, root)
            destination = args.output_dir if args.action == 'restore' else root / 'restored'
            unpack(data, destination)
            if stat.S_IMODE(destination.stat().st_mode) != 0o700:
                raise ValueError('Unexpected restored directory permissions')
            if any(stat.S_IMODE((destination / name).stat().st_mode) != 0o600 for name in NAMES):
                raise ValueError('Unexpected restored file permissions')
        print('PASS: 11 runtime files restored with 0700/0600 permissions; '
              + ('temporary plaintext cleaned' if args.action == 'verify' else 'operator must clean restore directory'))
        return 0
    except Exception:
        print('Vault bundle operation failed; secret details suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
