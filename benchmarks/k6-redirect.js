import http from 'k6/http';
import { check, fail } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://localhost';
const targetRps = Number(__ENV.TARGET_RPS || 500);
const duration = __ENV.DURATION || '60s';
const datasetSize = Number(__ENV.DATASET_SIZE || 1000);
const summaryPath = __ENV.SUMMARY_PATH || 'redirect-summary.json';

export const options = {
  scenarios: {
    redirects: {
      executor: 'constant-arrival-rate',
      rate: targetRps,
      timeUnit: '1s',
      duration,
      preAllocatedVUs: Math.max(50, Math.ceil(targetRps / 2)),
      maxVUs: Math.max(200, targetRps * 2),
    },
  },
  thresholds: {
    'http_req_failed{name:redirect}': ['rate<0.01'],
    'http_req_duration{name:redirect}': ['p(95)<500'],
  },
};

export function setup() {
  const suffix = String(Date.now());
  const codes = [];
  for (let index = 0; index < datasetSize; index += 1) {
    const shortCode = `Bench${suffix}${index}`;
    const response = http.post(
      `${baseUrl}/api/v1/urls`,
      JSON.stringify({
        originalUrl: `https://example.com/benchmark/${index}`,
        customAlias: shortCode,
      }),
      { headers: { 'Content-Type': 'application/json' }, tags: { name: 'setup-create' } },
    );
    if (response.status === 201) codes.push(shortCode);
  }

  for (const shortCode of codes) {
    http.get(`${baseUrl}/${shortCode}`, {
      redirects: 0,
      tags: { name: 'setup-warm' },
    });
  }
  if (codes.length === 0) fail('Benchmark setup did not create any URLs');
  return { codes };
}

export default function (data) {
  const shortCode = data.codes[Math.floor(Math.random() * data.codes.length)];
  const response = http.get(`${baseUrl}/${shortCode}`, {
    redirects: 0,
    tags: { name: 'redirect' },
  });
  check(response, { 'redirect returns 302': (result) => result.status === 302 });
}

export function handleSummary(data) {
  return { [summaryPath]: JSON.stringify(data, null, 2), stdout: '' };
}
