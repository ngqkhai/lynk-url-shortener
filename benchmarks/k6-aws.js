import http from 'k6/http';
import { check, fail } from 'k6';
const base = __ENV.BASE_URL || 'https://lynk.codes';
export const options = {
  scenarios: {
    metadata: {
      executor: 'constant-arrival-rate',
      rate: 2,
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 2,
      maxVUs: 10,
      exec: 'metadata',
    },
    redirect: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 2,
      maxVUs: 10,
      exec: 'redirect',
    },
  },
  thresholds: { checks: ['rate==1'], http_req_failed: ['rate==0'] },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};
export function setup() {
  const credentials = {
    email: `aws-bench-${Date.now()}@example.com`,
    password: 'long-local-benchmark-password',
  };
  const json = { headers: { 'Content-Type': 'application/json' } };
  if (http.post(`${base}/api/v1/auth/register`, JSON.stringify(credentials), json).status !== 201)
    fail('register failed');
  const login = http.post(`${base}/api/v1/auth/login`, JSON.stringify(credentials), json);
  if (login.status !== 200) fail('login failed');
  const pair = login.json(),
    code = `AwsBench${Date.now()}`;
  if (
    http.post(
      `${base}/api/v1/urls`,
      JSON.stringify({ customAlias: code, originalUrl: 'https://example.com' }),
      { headers: { ...json.headers, Authorization: `Bearer ${pair.accessToken}` } },
    ).status !== 201
  )
    fail('create failed');
  http.get(`${base}/${code}`, { redirects: 0 });
  return { ...pair, code };
}
export function metadata(data) {
  const r = http.get(`${base}/api/v1/urls/${data.code}`, {
    headers: { Authorization: `Bearer ${data.accessToken}` },
    tags: { name: 'metadata' },
  });
  check(r, { 'owner metadata 200': (r) => r.status === 200 });
}
export function redirect(data) {
  const r = http.get(`${base}/${data.code}`, { redirects: 0, tags: { name: 'redirect' } });
  check(r, { 'public redirect 302': (r) => r.status === 302 });
}
export function teardown(data) {
  http.post(`${base}/api/v1/auth/logout`, JSON.stringify({ refreshToken: data.refreshToken }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
export function handleSummary(data) {
  return {
    '/results/aws-summary.json': JSON.stringify(
      { metrics: data.metrics, root_group: data.root_group, state: data.state },
      null,
      2,
    ),
  };
}
