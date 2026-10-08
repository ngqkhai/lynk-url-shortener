#!/usr/bin/env python3
"""Runner-side SSM transport: validates arguments, polls terminal status, redacts no secrets."""
import json
import os
import re
import subprocess
import time


def aws(*args):
    return subprocess.check_output(['aws', *args], text=True)


sha = os.environ['RELEASE_SHA']
action = os.environ['DEPLOY_ACTION']
revision = os.environ['HELM_REVISION']
assert re.fullmatch(r'[0-9a-f]{40}', sha)
assert action in ('deploy', 'rollback') and re.fullmatch(r'[0-9]+', revision)
bucket = os.environ['ARTIFACT_BUCKET']
instance = os.environ['INSTANCE_ID']
assert re.fullmatch(r'[a-z0-9-]+', bucket) and re.fullmatch(r'i-[0-9a-f]+', instance)
if os.environ.get('UPLOAD_RELEASE') == 'true':
    # Never overwrite an already published release with a different bundle.
    key = 'releases/' + sha + '/release.sha256'
    try:
        existing = aws('s3', 'cp', 's3://' + bucket + '/' + key, '-')
    except subprocess.CalledProcessError:
        existing = None
    expected = open('release-upload/release.sha256').read()
    if existing is not None and existing != expected:
        raise SystemExit('Release already exists with a different checksum')
    for name in ['release.tar.gz', 'release.sha256']:
        aws('s3', 'cp', 'release-upload/' + name, 's3://' + bucket + '/releases/' + sha + '/' + name, '--only-show-errors')
command = json.loads(aws('ssm', 'send-command', '--instance-ids', instance,
    '--document-name', 'LynkDeploy', '--parameters', json.dumps({'ReleaseId':[sha], 'Action':[action], 'Revision':[revision]}),
    '--output-s3-bucket-name', bucket, '--output-s3-key-prefix', 'deploy-logs/' + sha,
    '--output', 'json'))['Command']['CommandId']
print('SSM command:', command, flush=True)
deadline = time.monotonic() + 3660
while time.monotonic() < deadline:
    try:
        result = json.loads(aws('ssm', 'get-command-invocation', '--command-id', command, '--instance-id', instance, '--output', 'json'))
    except subprocess.CalledProcessError:
        time.sleep(10)
        continue
    if result['Status'] in ('Pending', 'InProgress', 'Delayed'):
        time.sleep(10)
        continue
    print(result.get('StandardOutputContent',''))
    print(result.get('StandardErrorContent',''))
    print('Full output: s3://' + bucket + '/deploy-logs/' + sha + '/' + command)
    if result['Status'] != 'Success':
        raise SystemExit('Deployment failed: ' + result['Status'])
    break
else:
    # Do not cancel a command that may be running migration/rollback.
    raise SystemExit('Polling deadline exceeded; inspect SSM before retrying')
