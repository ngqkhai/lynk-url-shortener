#!/usr/bin/env python3
"""Opt-in reversible resilience checks on the local lynk-local deployment."""
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def request(path, method='GET', payload=None, token=None):
    headers = {'Host': 'lynk.localhost', 'content-type': 'application/json'}
    if token:
        headers['authorization'] = f'Bearer {token}'
    req = urllib.request.Request('http://127.0.0.1' + path, method=method, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
    try:
        response = client.open(req, timeout=40)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    return response.status, json.loads(body) if body and response.headers.get('content-type', '').startswith('application/json') else None


def kubectl(*args):
    return subprocess.check_output(['kubectl', '-n', 'lynk-local', *args], text=True).strip()


def db(service, database, query):
    return kubectl('exec', f'{service}-0', '--', 'psql', '-U', 'lynk', '-d', database, '-Atc', query)


def wait(predicate, label):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    raise AssertionError(f'Timeout: {label}')


credentials = {'email': f'kind-failure-{uuid.uuid4().hex}@example.com', 'password': 'long-local-test-password'}
assert request('/api/v1/auth/register', 'POST', credentials)[0] == 201
status, pair = request('/api/v1/auth/login', 'POST', credentials)
assert status == 200
access = pair['accessToken']
code = 'KindCold' + uuid.uuid4().hex[:12]
kubectl('scale', 'statefulset/kafka', '--replicas=0')
try:
    kubectl('wait', '--for=delete', 'pod/kafka-0', '--timeout=90s')
    assert request('/api/v1/urls', 'POST', {'originalUrl': 'https://example.com/kind-cold', 'customAlias': code}, access)[0] == 201
    assert db('url-postgres', 'lynk_urls', f"select count(*) from url_outbox where aggregate_key='{code}' and published_at is null") == '1'
    assert db('redirect-postgres', 'lynk_redirects', f"select count(*) from redirect_urls where short_code='{code}'") == '0'
    assert request('/' + code)[0] == 302
finally:
    kubectl('scale', 'statefulset/kafka', '--replicas=1')
kubectl('rollout', 'status', 'statefulset/kafka', '--timeout=180s')
wait(lambda: db('url-postgres', 'lynk_urls', f"select count(*) from url_outbox where aggregate_key='{code}' and published_at is not null") == '1', 'outbox publish recovery')
kubectl('rollout', 'restart', 'deployment/redirect-service')
kubectl('rollout', 'status', 'deployment/redirect-service', '--timeout=180s')
recovered = 'KindRecovered' + uuid.uuid4().hex[:10]
assert request('/api/v1/urls', 'POST', {'originalUrl': 'https://example.com', 'customAlias': recovered}, access)[0] == 201
wait(lambda: db('redirect-postgres', 'lynk_redirects', f"select count(*) from redirect_urls where short_code='{recovered}'") == '1', 'consumer sync before click after restart')
kubectl('scale', 'deployment/auth-service', '--replicas=0')
try:
    kubectl('wait', '--for=delete', 'pod', '-l', 'app=auth-service', '--timeout=90s')
    assert request('/api/v1/urls/' + code, token=access)[0] >= 500
    assert request('/' + code)[0] == 302
finally:
    kubectl('scale', 'deployment/auth-service', '--replicas=1')
kubectl('rollout', 'status', 'deployment/auth-service', '--timeout=180s')
wait(lambda: request('/api/v1/auth/me', token=access)[0] == 200, 'gateway endpoint recovery after auth rollout')
print('PASS kind: Kafka PVC restart, 201 pending outbox, HTTP cold miss 302, backlog recovery, consumer restart, auth outage fail closed/public redirect')
