#!/usr/bin/env python3
"""Create and strictly validate a replacement Lynk mTLS authority and leaf identities."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('OpenSSL operation failed; details suppressed')
    return result.stdout


def create(output, openssl='openssl'):
    if output.exists():
        raise ValueError('Refusing to overwrite PKI output directory')
    output.mkdir(mode=0o700, parents=True)
    try:
        (output / 'ca.cnf').write_text('''[req]\ndistinguished_name=dn\nx509_extensions=v3_ca\nprompt=no\n[dn]\nCN=Lynk local CA\n[v3_ca]\nbasicConstraints=critical,CA:true,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n''')
        (output / 'server.cnf').write_text('''[req]\ndistinguished_name=dn\nprompt=no\n[dn]\nCN=auth-service-gateway\n[server]\nbasicConstraints=critical,CA:false\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:auth-service-gateway,DNS:auth-service-gateway.lynk-aws.svc,DNS:localhost\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n''')
        (output / 'client.cnf').write_text('''[req]\ndistinguished_name=dn\nprompt=no\n[dn]\nCN=lynk-traefik\n[client]\nbasicConstraints=critical,CA:false\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=clientAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n''')
        commands = [
            [openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes', '-days', '365', '-config', str(output / 'ca.cnf'), '-keyout', str(output / 'ca-signing.key'), '-out', str(output / 'ca.crt')],
            [openssl, 'req', '-new', '-newkey', 'rsa:2048', '-sha256', '-nodes', '-config', str(output / 'server.cnf'), '-keyout', str(output / 'server.key'), '-out', str(output / 'server.csr')],
            [openssl, 'x509', '-req', '-sha256', '-days', '365', '-in', str(output / 'server.csr'), '-CA', str(output / 'ca.crt'), '-CAkey', str(output / 'ca-signing.key'), '-CAcreateserial', '-extfile', str(output / 'server.cnf'), '-extensions', 'server', '-out', str(output / 'server.crt')],
            [openssl, 'req', '-new', '-newkey', 'rsa:2048', '-sha256', '-nodes', '-config', str(output / 'client.cnf'), '-keyout', str(output / 'client.key'), '-out', str(output / 'client.csr')],
            [openssl, 'x509', '-req', '-sha256', '-days', '365', '-in', str(output / 'client.csr'), '-CA', str(output / 'ca.crt'), '-CAkey', str(output / 'ca-signing.key'), '-CAserial', str(output / 'ca.srl'), '-extfile', str(output / 'client.cnf'), '-extensions', 'client', '-out', str(output / 'client.crt')],
        ]
        for command in commands:
            run(command)
        for name in ('ca-signing.key', 'server.key', 'client.key'):
            (output / name).chmod(0o600)
        for name in ('server.csr', 'client.csr', 'ca.srl', 'ca.cnf', 'server.cnf', 'client.cnf'):
            (output / name).unlink()
        validate(output, openssl)
        return {name: (output / name).stat().st_size for name in ('ca.crt', 'ca-signing.key', 'server.crt', 'server.key', 'client.crt', 'client.key')}
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def validate(root, openssl='openssl'):
    for identity in ('server', 'client'):
        run([openssl, 'pkey', '-in', str(root / f'{identity}.key'), '-pubout', '-outform', 'PEM'])
        cert_pub = run([openssl, 'x509', '-in', str(root / f'{identity}.crt'), '-pubkey', '-noout'])
        key_pub = run([openssl, 'pkey', '-in', str(root / f'{identity}.key'), '-pubout'])
        if cert_pub != key_pub:
            raise ValueError('Certificate and private key do not match')
    run([openssl, 'verify', '-CAfile', str(root / 'ca.crt'), '-purpose', 'sslserver', '-verify_hostname', 'auth-service-gateway.lynk-aws.svc', str(root / 'server.crt')])
    run([openssl, 'verify', '-CAfile', str(root / 'ca.crt'), '-purpose', 'sslclient', str(root / 'client.crt')])
    server = run([openssl, 'x509', '-in', str(root / 'server.crt'), '-noout', '-subject', '-ext', 'subjectAltName,extendedKeyUsage'])
    client = run([openssl, 'x509', '-in', str(root / 'client.crt'), '-noout', '-subject', '-ext', 'extendedKeyUsage'])
    if 'CN = auth-service-gateway' not in server or 'DNS:auth-service-gateway.lynk-aws.svc' not in server or 'TLS Web Server Authentication' not in server:
        raise ValueError('Server identity contract mismatch')
    if 'CN = lynk-traefik' not in client or 'TLS Web Client Authentication' not in client:
        raise ValueError('Client identity contract mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--openssl', default='openssl')
    args = parser.parse_args()
    try:
        sizes = create(args.output_dir, args.openssl)
        print('PASS: new CA and mTLS leaf identities validated; six output files; byte sizes=' + ','.join(f'{key}:{value}' for key, value in sizes.items()))
        return 0
    except Exception:
        print('PKI preparation failed; details suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
