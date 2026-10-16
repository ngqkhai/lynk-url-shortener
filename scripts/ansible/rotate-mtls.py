#!/usr/bin/env python3
"""Run one guarded mTLS rotation phase through the pinned Ansible/SSM inventory."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'infra/ansible/vault/aws-demo.tar.gz.vault'


def run_phase(phase, bundle, password_file, overlap, executable='ansible-playbook', vault='ansible-vault', runner=subprocess.run):
    os.umask(0o077)
    inventory = ROOT / 'infra/ansible/inventory.py'
    result = runner([sys.executable, str(inventory), '--list'], capture_output=True, text=True)
    if result.returncode or json.loads(result.stdout).get('all', {}).get('hosts') != ['lynk']:
        raise RuntimeError('Terraform inventory must resolve exactly one Lynk host')
    with tempfile.TemporaryDirectory(prefix='lynk-mtls-rotation-') as directory:
        root = Path(directory)
        ansible_tmp = root / 'ansible-tmp'
        ansible_tmp.mkdir(mode=0o700)
        source = root / 'runtime'
        restored = runner([sys.executable, str(ROOT / 'scripts/secrets/vault-bundle.py'), 'restore',
                           '--bundle', str(bundle), '--ansible-vault', vault,
                           '--password-file', str(password_file), '--output-dir', str(source)], capture_output=True, text=True)
        if restored.returncode:
            raise RuntimeError('Encrypted runtime restoration failed; details suppressed')
        # Validate certificate role, trust, host identity and key match before any remote mutation.
        for identity, purpose in (('server', 'sslserver'), ('client', 'sslclient')):
            subprocess.run(['openssl', 'verify', '-CAfile', str(source / 'ca.crt'), '-purpose', purpose,
                            *(['-verify_hostname', 'auth-service-gateway.lynk-aws.svc'] if identity == 'server' else []),
                            str(source / f'{identity}.crt')], check=True, capture_output=True)
            cert = subprocess.run(['openssl', 'x509', '-in', str(source / f'{identity}.crt'), '-pubkey', '-noout'], check=True, capture_output=True).stdout
            key = subprocess.run(['openssl', 'pkey', '-in', str(source / f'{identity}.key'), '-pubout'], check=True, capture_output=True).stdout
            if cert != key:
                raise RuntimeError('Certificate and private key mismatch')
            subject = subprocess.run(['openssl', 'x509', '-in', str(source / f'{identity}.crt'), '-noout', '-subject'], check=True, capture_output=True).stdout.decode()
            required_subject = 'CN = auth-service-gateway' if identity == 'server' else 'CN = lynk-traefik'
            if required_subject not in subject:
                raise RuntimeError('Certificate identity does not match the Lynk mTLS contract')
        if phase == 'stage':
            if not overlap or not overlap.is_file():
                raise RuntimeError('Stage phase requires an overlap CA bundle')
            # Require the configured CA to be one member of the overlap bundle.
            new_ca = subprocess.run(['openssl', 'x509', '-in', str(source / 'ca.crt'), '-noout', '-fingerprint', '-sha256'], check=True, capture_output=True).stdout.strip()
            overlap_data = overlap.read_bytes()
            matches = False
            valid_fingerprints = set()
            for index, piece in enumerate(overlap_data.split(b'-----END CERTIFICATE-----')):
                if b'-----BEGIN CERTIFICATE-----' not in piece:
                    continue
                candidate = root / f'overlap-{index}.pem'
                candidate.write_bytes(piece + b'-----END CERTIFICATE-----\n')
                fingerprint = subprocess.run(['openssl', 'x509', '-in', str(candidate), '-noout', '-fingerprint', '-sha256'], capture_output=True)
                if fingerprint.returncode == 0:
                    valid_fingerprints.add(fingerprint.stdout.strip())
                    if fingerprint.stdout.strip() == new_ca:
                        matches = True
            if not matches or len(valid_fingerprints) < 2:
                raise RuntimeError('Overlap CA bundle must contain both current and replacement trust anchors')
        variables = {'lynk_mtls_phase': phase, 'lynk_mtls_source_dir': str(source)}
        if phase == 'stage':
            variables['lynk_mtls_overlap_file'] = str(overlap.resolve())
        variable_file = root / 'variables.json'
        variable_file.write_text(json.dumps(variables))
        variable_file.chmod(0o600)
        command = [executable, '-i', str(inventory), str(ROOT / 'infra/ansible/rotate-mtls.yml'), '--extra-vars', '@' + str(variable_file)]
        environment = os.environ.copy()
        environment['ANSIBLE_LOCAL_TEMP'] = str(ansible_tmp)
        return runner(command, env=environment).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True, choices=('stage', 'finalize'))
    parser.add_argument('--bundle', type=Path, default=RUNTIME)
    parser.add_argument('--password-file', type=Path, required=True)
    parser.add_argument('--overlap-file', type=Path)
    args = parser.parse_args()
    if shutil.which('session-manager-plugin') is None:
        parser.error('Pinned Session Manager plugin must be on controller PATH')
    executable, vault = shutil.which('ansible-playbook'), shutil.which('ansible-vault')
    if not executable or not vault:
        parser.error('Pinned Ansible must be on controller PATH')
    try:
        return run_phase(args.phase, args.bundle, args.password_file, args.overlap_file, executable, vault)
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError):
        print('mTLS rotation phase failed; temporary plaintext cleaned when process exited normally', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
