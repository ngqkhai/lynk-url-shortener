#!/usr/bin/env python3
"""Update only existing, named Lynk mTLS Secret data keys on the K3s node."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

NAMESPACE = 'lynk-aws'
SECRETS = {
    'ca': ('lynk-gateway-ca', {'ca.crt': 'ca.crt'}),
    'server': ('lynk-gateway-server', {'ca.crt': 'ca.crt', 'server.crt': 'server.crt', 'server.key': 'server.key'}),
    'client': ('lynk-gateway-client', {'tls.crt': 'client.crt', 'tls.key': 'client.key'}),
}


def kubectl(arguments, input_data=None):
    result = subprocess.run(['/usr/local/bin/kubectl'] + arguments, input=input_data,
                            capture_output=True)
    if result.returncode:
        raise RuntimeError('Kubernetes Secret operation failed; output suppressed')
    return result.stdout


def apply_secret(kind, directory, ca_file=None):
    name, keys = SECRETS[kind]
    raw = json.loads(kubectl(['get', 'secret', name, '-n', NAMESPACE, '-o', 'json']))
    if raw.get('metadata', {}).get('name') != name:
        raise ValueError('Unexpected Secret identity')
    data = raw.setdefault('data', {})
    for key, filename in keys.items():
        path = Path(ca_file) if key == 'ca.crt' and ca_file else Path(directory) / filename
        data[key] = base64.b64encode(path.read_bytes()).decode('ascii')
    kubectl(['apply', '-f', '-'], json.dumps(raw, separators=(',', ':')).encode())


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in SECRETS:
        return 2
    kind, directory, ca_file = sys.argv[1:]
    if os.geteuid() != 0:
        return 2
    try:
        apply_secret(kind, directory, ca_file or None)
        return 0
    except Exception:
        print('Secret update failed; values suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
