#!/usr/bin/env python3
"""Validate delivery configuration before any AWS credentials or commands are used."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-ssm', action='store_true')
    args = parser.parse_args()
    mode = os.environ.get('LYNK_DEPLOY_MODE') or 'paused'
    if mode not in ('paused', 'ssm', 'argocd'):
        print('Invalid LYNK_DEPLOY_MODE; expected paused, ssm or argocd', file=sys.stderr)
        return 1
    if args.require_ssm and mode != 'ssm':
        print('Legacy deployment blocked: mode=' + mode, file=sys.stderr)
        return 1
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with Path(output).open('a') as stream:
            stream.write('mode=' + mode + '\n')
    print('Deployment mode: ' + mode)
    if mode == 'paused':
        print('Delivery paused; source, infrastructure and GitOps checks still run.')
    elif mode == 'argocd':
        print('ArgoCD delivery is reserved for later checkpoints; legacy SSM is blocked.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
