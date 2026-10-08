import http from 'k6/http';
import { check, fail } from 'k6';
import { Trend } from 'k6/metrics';
const gateway = __ENV.GATEWAY_URL || 'http://traefik:8080';
const baseline = new Trend('internal_jwt_metadata_ms', true);
const phantom = new Trend('phantom_metadata_ms', true);
export const options = {
  scenarios: {
    internal: { executor: 'constant-vus', vus: 1, duration: '20s', exec: 'internal' },
    gateway: { executor: 'constant-vus', vus: 1, duration: '20s', exec: 'gatewayRequest' },
  },
  tlsAuth: [
    {
      domains: ['auth-service-gateway'],
      cert: open('/tls/client.crt'),
      key: open('/tls/client.key'),
    },
  ],
  thresholds: { checks: ['rate==1'], http_req_failed: ['rate==0'] },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};
export function setup() {
  const credentials = {
    email: `latency-${Date.now()}@example.com`,
    password: 'long-local-benchmark-password',
  };
  const json = { headers: { 'Content-Type': 'application/json' } };
  if (
    http.post(`${gateway}/api/v1/auth/register`, JSON.stringify(credentials), json).status !== 201
  )
    fail('Register failed');
  const login = http.post(`${gateway}/api/v1/auth/login`, JSON.stringify(credentials), json);
  if (login.status !== 200) fail('Login failed');
  const opaque = login.json().accessToken;
  const code = `Latency${Date.now()}`;
  if (
    http.post(
      `${gateway}/api/v1/urls`,
      JSON.stringify({ customAlias: code, originalUrl: 'https://example.com' }),
      { headers: { ...json.headers, Authorization: `Bearer ${opaque}` } },
    ).status !== 201
  )
    fail('Create failed');
  // This setup is an authorized gateway test harness; the JWT stays inside the harness.
  const exchange = http.get('https://auth-service-gateway:3005/internal/auth/forward', {
    headers: { Authorization: `Bearer ${opaque}` },
  });
  if (exchange.status !== 200) fail('mTLS exchange failed');
  return {
    opaque,
    refreshToken: login.json().refreshToken,
    jwt: exchange.headers.Authorization,
    code,
  };
}
export function internal(data) {
  const response = http.get(`http://url-service:3001/api/v1/urls/${data.code}`, {
    headers: { Authorization: data.jwt },
    tags: { name: 'internal-jwt-metadata' },
  });
  baseline.add(response.timings.duration);
  check(response, { 'internal metadata 200': (r) => r.status === 200 });
}
export function gatewayRequest(data) {
  const response = http.get(`${gateway}/api/v1/urls/${data.code}`, {
    headers: { Authorization: `Bearer ${data.opaque}` },
    tags: { name: 'phantom-metadata' },
  });
  phantom.add(response.timings.duration);
  check(response, { 'phantom metadata 200': (r) => r.status === 200 });
}
export function teardown(data) {
  http.post(`${gateway}/api/v1/auth/logout`, JSON.stringify({ refreshToken: data.refreshToken }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
export function handleSummary(data) {
  // k6 includes setup_data by default: omit token-bearing setup data from artifacts.
  const summary = {
    metrics: data.metrics,
    root_group: data.root_group,
    state: data.state,
    summaryTrendStats: options.summaryTrendStats,
  };
  return { '/results/phantom-summary.json': JSON.stringify(summary, null, 2) };
}
