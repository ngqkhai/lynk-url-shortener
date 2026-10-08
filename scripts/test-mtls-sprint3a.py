#!/usr/bin/env python3
"""Probe the real private auth listener using independent TLS client identities."""
import json
import os
import socket
import ssl
import subprocess
from pathlib import Path

keys = Path(os.environ['LYNK_KEY_DIR'])
project = os.environ.get('LYNK_COMPOSE_PROJECT', 'lynk-3a-test')
networks = json.loads(subprocess.check_output(['docker', 'inspect', f'{project}-auth-service-1', '--format', '{{json .NetworkSettings.Networks}}'], text=True))
host = next(iter(networks.values()))['IPAddress']


def certificate(name, ca='ca', days='1'):
    subprocess.run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', f'/CN={name}', '-keyout', str(keys / f'{name}.key'), '-out', str(keys / f'{name}.csr')], check=True, capture_output=True)
    subprocess.run(['openssl', 'x509', '-req', '-in', str(keys / f'{name}.csr'), '-CA', str(keys / f'{ca}.crt'), '-CAkey', str(keys / f'{ca}.key'), '-CAcreateserial', '-days', days, '-out', str(keys / f'{name}.crt')], check=True, capture_output=True)


def probe(identity=None, hostname='auth-service-gateway'):
    context = ssl.create_default_context(cafile=str(keys / 'ca.crt'))
    if identity:
        context.load_cert_chain(str(keys / f'{identity}.crt'), str(keys / f'{identity}.key'))
    with socket.create_connection((host, 3005), timeout=5) as connection:
        with context.wrap_socket(connection, server_hostname=hostname) as secure:
            secure.sendall(b'GET /internal/auth/forward HTTP/1.1\r\nHost: auth-service-gateway\r\nConnection: close\r\n\r\n')
            data = secure.recv(4096)
            return int(data.split(b' ')[1])


def tls_failure(identity=None, hostname='auth-service-gateway'):
    try:
        probe(identity, hostname)
    except (ssl.SSLError, OSError, IndexError):
        return
    raise AssertionError(f'TLS client {identity} unexpectedly accepted')


assert probe('client') == 401  # Authenticated gateway still needs a user token.
tls_failure()
certificate('wrong-identity')
assert probe('wrong-identity') == 403
certificate('expired', days='-1')
tls_failure('expired')
subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=Other CA', '-keyout', str(keys / 'other.key'), '-out', str(keys / 'other.crt')], check=True, capture_output=True)
certificate('wrong-ca', ca='other')
tls_failure('wrong-ca')
tls_failure('client', hostname='wrong-hostname')
print('PASS: mTLS missing certificate, wrong CA, wrong identity, expired certificate, wrong server SAN')
