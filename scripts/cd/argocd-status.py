#!/usr/bin/env python3
"""Wait for one exact release using bounded, read-only Kubernetes requests."""
import argparse
import json
import re
import subprocess
import sys
import time


class Pending(Exception):
    """The requested release can still converge."""


class Terminal(Exception):
    """The request cannot succeed without intervention."""


def require(condition, message):
    if not condition:
        raise Pending(message)


def read_json(run, *args):
    try:
        value = json.loads(run(*args))
        if not isinstance(value, dict):
            raise ValueError('not an object')
        return value
    except (ValueError, TypeError) as error:
        raise Terminal('Kubernetes returned invalid JSON') from error


def check_once(run, revision, sha, digests):
    app = read_json(run, 'get', 'application', 'aws-demo', '-n', 'argocd', '-o', 'json')
    state = app.get('status', {})
    operation = state.get('operationState', {})
    result = operation.get('syncResult', {})
    if result.get('revision') == revision:
        if operation.get('phase') in ('Failed', 'Error'):
            raise Terminal('Argo operation for the requested revision failed')
        if any(item.get('hookPhase') in ('Failed', 'Error') for item in result.get('resources', [])):
            raise Terminal('Argo hook for the requested revision failed')
    require(state.get('sync', {}).get('revision') == revision, 'Argo has not observed the requested revision')
    require(state.get('sync', {}).get('status') == 'Synced', 'Argo is not Synced')
    require(state.get('health', {}).get('status') == 'Healthy', 'Argo is not Healthy')
    require(operation.get('phase') == 'Succeeded' and result.get('revision') == revision,
            'Argo has not completed the requested operation')
    for name, digest in digests.items():
        deployment = read_json(run, 'get', 'deployment', name, '-n', 'lynk-aws', '-o', 'json')
        spec, status = deployment.get('spec', {}), deployment.get('status', {})
        replicas = spec.get('replicas', 1)
        require(replicas > 0 and status.get('readyReplicas', 0) >= replicas, name + ' is not fully Ready')
        require(status.get('observedGeneration', 0) >= deployment.get('metadata', {}).get('generation', 1),
                name + ' controller has not observed the Deployment generation')
        containers = spec.get('template', {}).get('spec', {}).get('containers', [])
        require(any(c.get('name') == name and c.get('image', '').endswith('@' + digest) for c in containers),
                name + ' Deployment digest has not converged')
        pods = read_json(run, 'get', 'pods', '-n', 'lynk-aws', '-l', 'app=' + name, '-o', 'json')
        running = [p for p in pods.get('items', []) if p.get('status', {}).get('phase') == 'Running'
                   and not p.get('metadata', {}).get('deletionTimestamp')]
        require(len(running) >= replicas, name + ' does not have the requested Running Pods')
        for pod in running:
            require(any(c.get('name') == name and c.get('ready') and c.get('imageID', '').endswith('@' + digest)
                        for c in pod.get('status', {}).get('containerStatuses', [])),
                    name + ' runtime digest/readiness has not converged')
            # Check every live Pod, rather than an arbitrary Pod chosen by deployment/name.
            logs = run('logs', pod['metadata']['name'], '-n', 'lynk-aws', '-c', name, '--tail=100')
            found = False
            for line in logs.splitlines():
                try:
                    record = json.loads(line)
                    found = found or (isinstance(record, dict) and record.get('releaseSha') == sha)
                except ValueError:
                    continue
            require(found, name + ' startup logs do not identify the requested release')
    raw_job = run('get', 'job', 'lynk-postsync-smoke', '-n', 'lynk-aws', '-o', 'json', '--ignore-not-found')
    if raw_job.strip():
        try:
            job = json.loads(raw_job)
            if not isinstance(job, dict):
                raise ValueError('not an object')
        except ValueError as error:
            raise Terminal('Kubernetes returned invalid smoke Job JSON') from error
        failed = any(c.get('type') == 'Failed' and c.get('status') == 'True'
                     for c in job.get('status', {}).get('conditions', []))
        if failed:
            raise Terminal('PostSync smoke Job failed')
        require(job.get('status', {}).get('succeeded', 0) >= 1, 'PostSync smoke has not completed')
        digest = digests['url-service']
        require(any(c.get('image', '').endswith('@' + digest)
                    for c in job.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])),
                'PostSync Job digest does not match')
        pods = read_json(run, 'get', 'pods', '-n', 'lynk-aws', '-l', 'app=lynk-postsync-smoke', '-o', 'json')
        require(any(p.get('status', {}).get('phase') == 'Succeeded' and any(
                    c.get('name') == 'smoke' and c.get('imageID', '').endswith('@' + digest)
                    for c in p.get('status', {}).get('containerStatuses', [])) for p in pods.get('items', [])),
                'PostSync Pod runtime digest does not match')
    else:
        hooks = [item for item in result.get('resources', []) if item.get('name') == 'lynk-postsync-smoke'
                 and item.get('hookType') == 'PostSync' and item.get('namespace') == 'lynk-aws'
                 and item.get('kind') == 'Job']
        require(len(hooks) == 1 and hooks[0].get('hookPhase') == 'Succeeded',
                'Argo operation history does not record a successful PostSync smoke hook')
        require(any(image.endswith('@' + digests['url-service']) for image in hooks[0].get('images', [])),
                'Recorded PostSync digest does not match')
    return {'values_revision': revision, 'release_sha': sha, 'status': 'Healthy', 'smoke': 'Succeeded'}


def kubectl_runner(deadline, clock=time.monotonic):
    def run(*args):
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError('Argo release verification deadline exceeded')
        try:
            completed = subprocess.run(['/usr/local/bin/kubectl', '--request-timeout=15s', *args],
                                       capture_output=True, text=True, timeout=min(20, remaining))
        except subprocess.TimeoutExpired as error:
            raise Pending('Kubernetes request timed out') from error
        except OSError as error:
            raise Terminal('kubectl could not be executed') from error
        if completed.returncode:
            message = completed.stderr.lower()
            if any(term in message for term in ('forbidden', 'unauthorized', 'permission denied')):
                raise Terminal('Kubernetes access denied')
            if any(term in message for term in ('notfound', 'not found', 'unable to connect', 'connection refused',
                                                'timeout', 'timed out', 'deadline exceeded', 'serviceunavailable',
                                                'temporarily unavailable', 'connection reset', 'unexpected eof')):
                raise Pending('Kubernetes resource/API is not available yet')
            raise Terminal('kubectl request failed; inspect access/configuration')
        return completed.stdout
    return run


def wait_for_release(check, deadline, clock=time.monotonic, sleep=time.sleep, report=lambda msg: print(msg, file=sys.stderr)):
    last_reason = None
    while clock() < deadline:
        try:
            result = check()
            if clock() >= deadline:
                break
            return result
        except Pending as error:
            reason = str(error)
            if reason != last_reason:
                report('Waiting: ' + reason)
                last_reason = reason
        sleep(min(10, max(0, deadline - clock())))
    raise TimeoutError('Argo release verification deadline exceeded')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('revision', 'sha', 'url_digest', 'redirect_digest', 'auth_digest'):
        parser.add_argument(name)
    args = parser.parse_args()
    if not all(re.fullmatch('[0-9a-f]{40}', x) for x in (args.revision, args.sha)):
        parser.error('invalid revision argument')
    if not all(re.fullmatch('sha256:[0-9a-f]{64}', x) for x in (args.url_digest, args.redirect_digest, args.auth_digest)):
        parser.error('invalid image digest argument')
    digests = dict(zip(('url-service', 'redirect-service', 'auth-service'),
                       (args.url_digest, args.redirect_digest, args.auth_digest)))
    deadline = time.monotonic() + 840
    run = kubectl_runner(deadline)
    try:
        result = wait_for_release(lambda: check_once(run, args.revision, args.sha, digests), deadline)
        print(json.dumps(result, sort_keys=True))
        return 0
    except TimeoutError as error:
        print(str(error), file=sys.stderr)
        return 124
    except (Terminal, KeyError, TypeError, AttributeError) as error:
        # Never print raw JSON/log data, which can contain sensitive configuration.
        print(str(error) if isinstance(error, Terminal) else 'Unexpected Kubernetes response structure', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
