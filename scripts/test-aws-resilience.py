#!/usr/bin/env python3
"""Reversible checks against the deployed single-node demo; credentials stay in memory."""
import json, subprocess, time, urllib.request, urllib.error, uuid
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
client=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def request(path,method='GET',body=None,token=None):
    headers={'content-type':'application/json'}
    if token: headers['authorization']='Bearer '+token
    req=urllib.request.Request('https://lynk.codes'+path,method=method,headers=headers,data=json.dumps(body).encode() if body is not None else None)
    try: r=client.open(req,timeout=30)
    except urllib.error.HTTPError as e:r=e
    b=r.read();return r.status,json.loads(b) if b and r.headers.get('content-type','').startswith('application/json') else None
ssh=['ssh','-i','/tmp/lynk-aws-admin','-p','2222','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','-o','UserKnownHostsFile=/tmp/lynk-aws-known-hosts','ubuntu@127.0.0.1']
def remote(cmd):return subprocess.check_output(ssh+[cmd],text=True,timeout=330).strip()
def wait(fn,label):
    end=time.monotonic()+120
    while time.monotonic()<end:
        try:
            if fn():return
        except (OSError,subprocess.SubprocessError):pass
        time.sleep(1)
    raise AssertionError('Timeout '+label)
credentials={'email':'aws-recovery-'+uuid.uuid4().hex+'@example.com','password':'long-local-test-password'}
assert request('/api/v1/auth/register','POST',credentials)[0]==201
status,pair=request('/api/v1/auth/login','POST',credentials);assert status==200
code='AwsCold'+uuid.uuid4().hex[:12]
remote('sudo kubectl -n lynk-aws scale statefulset/kafka --replicas=0; sudo kubectl -n lynk-aws wait --for=delete pod/kafka-0 --timeout=90s')
try:
    assert request('/api/v1/urls','POST',{'originalUrl':'https://example.com/recovery','customAlias':code},pair['accessToken'])[0]==201
    assert request('/'+code)[0]==302
finally: remote('sudo kubectl -n lynk-aws scale statefulset/kafka --replicas=1')
remote('sudo kubectl -n lynk-aws rollout status statefulset/kafka --timeout=240s')
program='const p=require("postgres");const s=p(process.env.DATABASE_URL,{max:1});s`select count(*) as n from url_outbox where published_at is null`.then(r=>{process.stdout.write(String(r[0].n));return s.end({timeout:3})}).catch(()=>process.exit(1))'
import shlex
wait(lambda:remote('sudo kubectl -n lynk-aws exec deployment/url-service -- node -e '+shlex.quote(program))=='0','outbox drain after broker recovery')
remote('sudo kubectl -n lynk-aws rollout restart deployment/url-service; sudo kubectl -n lynk-aws rollout status deployment/url-service --timeout=180s')
wait(lambda:request('/api/v1/urls/'+code,token=pair['accessToken'])[0]==200,'owner metadata after rollout')
assert request('/'+code)[0]==302
assert request('/api/v1/auth/logout','POST',{'refreshToken':pair['refreshToken']})[0]==204
print('PASS AWS: broker outage POST201/cold-miss302, recovery outbox drain, low-memory rollout, owner metadata/public redirect')
