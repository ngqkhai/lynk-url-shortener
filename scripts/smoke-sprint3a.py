#!/usr/bin/env python3
"""Real gateway acceptance checks; opaque tokens stay in memory."""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import shlex
from datetime import datetime, timezone

BASE = os.environ.get('LYNK_BASE_URL', 'http://127.0.0.1:8088')
KIND = os.environ.get('LYNK_SMOKE_KIND') == 'true'
AWS = os.environ.get('LYNK_SMOKE_AWS') == 'true'
SSM = os.environ.get('LYNK_SMOKE_SSM') == 'true'
if KIND:
    BASE = 'http://127.0.0.1'
COMPOSE = ['docker', 'compose', '-p', os.environ.get('LYNK_COMPOSE_PROJECT', 'lynk-3a-test'), '-f', 'infra/docker/compose.3a.yml', '--profile', 'gateway']


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def request(path, method='GET', payload=None, token=None, extra=None):
    headers = {'content-type': 'application/json', **(extra or {})}
    if KIND:
        headers['Host'] = 'lynk.localhost'
    if token:
        headers['authorization'] = f'Bearer {token}'
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
    try:
        response = opener.open(req, timeout=40)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    # Internal Authorization must never escape to the client, including ForwardAuth failures.
    assert response.headers.get('authorization') is None, 'Internal JWT leaked to client'
    return response.status, json.loads(body) if body and response.headers.get('content-type', '').startswith('application/json') else None, response.headers


def wait(predicate, label, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    raise AssertionError(f'Timeout: {label}')


def db(service, database, query):
    if AWS:
        app = {'url-postgres': 'url-service', 'redirect-postgres': 'redirect-service', 'auth-postgres': 'auth-service'}[service]
        program = 'const postgres=require("postgres");const s=postgres(process.env.DATABASE_URL,{max:1});s.unsafe(process.argv[1]).then(r=>{process.stdout.write(String(Object.values(r[0])[0]));return s.end({timeout:3})}).catch(e=>{process.stderr.write(e.message);process.exit(1)})'
        remote = 'sudo kubectl -n lynk-aws exec deployment/' + app + ' -- node -e ' + shlex.quote(program) + ' ' + shlex.quote(query)
        command = ['ssh', '-i', '/tmp/lynk-aws-admin', '-p', '2222', '-o', 'UserKnownHostsFile=/tmp/lynk-aws-known-hosts', 'ubuntu@127.0.0.1', remote]
        if SSM:
            command = ['kubectl', '-n', 'lynk-aws', 'exec', 'deployment/' + app, '--', 'node', '-e', program, query]
    elif KIND:
        command = ['kubectl', '-n', 'lynk-local', 'exec', f'{service}-0', '--', 'psql', '-U', 'lynk', '-d', database, '-Atc', query]
    else:
        command = COMPOSE + ['exec', '-T', service, 'psql', '-U', 'lynk', '-d', database, '-Atc', query]
    return subprocess.check_output(command, text=True).strip()


def account(label):
    credentials = {'email': f'{label}-{uuid.uuid4().hex}@example.com', 'password': 'long-local-test-password'}
    assert request('/api/v1/auth/register', 'POST', credentials)[0] == 201
    status, pair, _ = request('/api/v1/auth/login', 'POST', credentials)
    assert status == 200
    assert pair['accessToken'].startswith('at_') and pair['refreshToken'].startswith('rt_')
    assert pair['accessToken'].count('.') == 0
    return credentials, pair


wait(lambda: request('/health/ready')[0] == 200, 'URL gateway readiness')
wait(lambda: request('/api/v1/auth/login', 'POST', {})[0] == 400, 'public auth readiness')
wait(lambda: request('/api/v1/auth/me')[0] == 401, 'private ForwardAuth readiness')
_, owner = account('owner')
_, other = account('other')
code = 'S3A' + uuid.uuid4().hex[:16]
body = {'originalUrl': 'https://example.com/sprint3a', 'customAlias': code, 'ownerId': str(uuid.uuid4())}
assert request('/api/v1/urls', 'POST', body)[0] == 401
assert request('/api/v1/urls', 'POST', body, 'forged.jwt.value', {'X-User-Id': str(uuid.uuid4()), 'X-Forwarded-User': 'admin'})[0] == 401
assert request('/api/v1/auth/me', token=owner['accessToken'])[0] == 200
assert request('/api/v1/urls', 'POST', body, owner['accessToken'])[0] == 201
# Prove replication before any redirect can invoke HTTP cold-miss hydration.
wait(lambda: db('redirect-postgres', 'lynk_redirects', f"select count(*) from redirect_urls where short_code='{code}' and owner_id is not null") == '1', 'Kafka replication before first click')
assert request(f'/api/v1/urls/{code}', token=owner['accessToken'])[0] == 200
assert request(f'/api/v1/urls/{code}', token=other['accessToken'])[0] == 404
assert request(f'/{code}')[0] == 302
assert request('/internal/urls/' + code)[0] == 404
assert request('/internal/auth/forward', token=owner['accessToken'])[0] == 404
status, second, _ = request('/api/v1/auth/refresh', 'POST', {'refreshToken': owner['refreshToken']})
assert status == 200
assert request('/api/v1/auth/me', token=owner['accessToken'])[0] == 200
assert request('/api/v1/auth/refresh', 'POST', {'refreshToken': owner['refreshToken']})[0] == 401
assert request('/api/v1/auth/me', token=second['accessToken'])[0] == 401
assert request('/api/v1/auth/logout', 'POST', {'refreshToken': other['refreshToken']})[0] == 204
assert request('/api/v1/auth/me', token=other['accessToken'])[0] == 401
assert request(f'/{code}')[0] == 302
print('PASS: opaque gateway, owner isolation, refresh reuse, logout, public redirect, replication before first click')

if not KIND and not AWS and os.environ.get('LYNK_FAILURE_TESTS', 'true') == 'true':
    _, live = account('failure')
    cold = 'Cold' + uuid.uuid4().hex[:16]
    subprocess.run(COMPOSE + ['stop', 'kafka'], check=True, stdout=subprocess.DEVNULL)
    try:
        assert request('/api/v1/urls', 'POST', {'originalUrl': 'https://example.com/cold', 'customAlias': cold}, live['accessToken'])[0] == 201
        assert db('url-postgres', 'lynk_urls', f"select count(*) from url_outbox where aggregate_key='{cold}' and published_at is null") == '1'
        assert request('/' + cold)[0] == 302
    finally:
        subprocess.run(COMPOSE + ['start', 'kafka'], check=True, stdout=subprocess.DEVNULL)
    wait(lambda: db('url-postgres', 'lynk_urls', f"select count(*) from url_outbox where aggregate_key='{cold}' and published_at is not null") == '1', 'outbox recovery', 120)
    # Separate event created after broker recovery proves a live consumer, without cold-miss writes.
    recovered = 'Recovered' + uuid.uuid4().hex[:12]
    assert request('/api/v1/urls', 'POST', {'originalUrl': 'https://example.com', 'customAlias': recovered}, live['accessToken'])[0] == 201
    wait(lambda: db('redirect-postgres', 'lynk_redirects', f"select count(*) from redirect_urls where short_code='{recovered}'") == '1', 'consumer recovery')
    subprocess.run(COMPOSE + ['stop', 'auth-postgres'], check=True, stdout=subprocess.DEVNULL)
    try:
        assert request('/api/v1/urls/' + code, token=live['accessToken'])[0] >= 500
        assert request('/' + code)[0] == 302
    finally:
        subprocess.run(COMPOSE + ['start', 'auth-postgres'], check=True, stdout=subprocess.DEVNULL)
    wait(lambda: request('/api/v1/auth/me', token=live['accessToken'])[0] == 200, 'auth DB recovery')
    # The consumer must hold offsets until PostgreSQL persistence succeeds.
    def offsets():
        program = "const {Kafka}=require('kafkajs');(async()=>{const a=new Kafka({brokers:['kafka:9092'],logLevel:0}).admin();await a.connect();const o=await a.fetchOffsets({groupId:'lynk-redirect-v1',topics:['url.created']});console.log(JSON.stringify(o));await a.disconnect();})().catch(()=>process.exit(1))"
        return subprocess.check_output(COMPOSE + ['exec', '-T', 'url-service', 'node', '-e', program], text=True).strip()
    wait(lambda: db('url-postgres', 'lynk_urls', 'select count(*) from url_outbox where published_at is null') == '0', 'outbox drain')
    time.sleep(2)
    baseline = offsets()
    durable = 'DbRetry' + uuid.uuid4().hex[:12]
    subprocess.run(COMPOSE + ['stop', 'redirect-postgres'], check=True, stdout=subprocess.DEVNULL)
    try:
        assert request('/api/v1/urls', 'POST', {'originalUrl': 'https://example.com/durable', 'customAlias': durable}, live['accessToken'])[0] == 201
        wait(lambda: db('url-postgres', 'lynk_urls', f"select count(*) from url_outbox where aggregate_key='{durable}' and published_at is not null") == '1', 'event published during read DB outage')
        time.sleep(4)
        assert offsets() == baseline, 'Consumer advanced offsets while its DB was unavailable'
    finally:
        subprocess.run(COMPOSE + ['start', 'redirect-postgres'], check=True, stdout=subprocess.DEVNULL)
    wait(lambda: db('redirect-postgres', 'lynk_redirects', f"select count(*) from redirect_urls where short_code='{durable}'") == '1', 'read DB recovery')
    subprocess.run(COMPOSE + ['restart', 'redirect-service'], check=True, stdout=subprocess.DEVNULL)
    after_restart = 'Restart' + uuid.uuid4().hex[:12]
    assert request('/api/v1/urls', 'POST', {'originalUrl': 'https://example.com', 'customAlias': after_restart}, live['accessToken'])[0] == 201
    wait(lambda: db('redirect-postgres', 'lynk_redirects', f"select count(*) from redirect_urls where short_code='{after_restart}'") == '1', 'consumer restart recovery')
    # Poison event followed by valid event on the same partition must not wedge delivery.
    event_code = 'Event' + uuid.uuid4().hex[:12]
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    _, me, _ = request('/api/v1/auth/me', token=live['accessToken'])
    event = {'eventId': str(uuid.uuid4()), 'eventType': 'url.created', 'schemaVersion': 1, 'occurredAt': timestamp, 'data': {'urlId': str(uuid.uuid4()), 'shortCode': event_code, 'originalUrl': 'https://example.com/event', 'createdAt': timestamp, 'expiresAt': None, 'ownerId': me['user']['id']}}
    program = "const {Kafka}=require('kafkajs');(async()=>{const k=new Kafka({brokers:['kafka:9092'],logLevel:0});const p=k.producer({allowAutoTopicCreation:false});await p.connect();await p.send({topic:'url.created',acks:-1,messages:JSON.parse(process.argv[1]).map(value=>({partition:0,key:'acceptance',value}))});await p.disconnect();})().catch(()=>process.exit(1))"
    subprocess.run(COMPOSE + ['exec', '-T', 'url-service', 'node', '-e', program, json.dumps(['{bad json', json.dumps(event), json.dumps(event)])], check=True)
    wait(lambda: db('redirect-postgres', 'lynk_redirects', f"select count(*) from redirect_urls where short_code='{event_code}'") == '1', 'valid event after poison and duplicate')
    dlq = "const {Kafka}=require('kafkajs');(async()=>{const a=new Kafka({brokers:['kafka:9092'],logLevel:0}).admin();await a.connect();const o=await a.fetchTopicOffsets('url.created.dlq');console.log(o.reduce((n,p)=>n+Number(p.offset),0));await a.disconnect();})().catch(()=>process.exit(1))"
    wait(lambda: int(subprocess.check_output(COMPOSE + ['exec', '-T', 'url-service', 'node', '-e', dlq], text=True).strip()) > 0, 'poison DLQ acknowledgment')
    print('PASS: Kafka outage/outbox/cold miss/recovery; auth DB fail closed; read DB offset hold; consumer restart; poison DLQ and duplicate')
