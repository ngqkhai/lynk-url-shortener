import { FastifyInstance } from 'fastify';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { buildApp } from '../src/app.js';
import { Env } from '../src/config/env.js';
import { DatabaseClient } from '../src/infra/db.js';
import { RedirectCache } from '../src/infra/redis.js';
import { UrlSource } from '../src/infra/url-source.js';
import { RedirectStore } from '../src/repositories/redirect.repository.js';

describe('Redirect health routes', () => {
  let app: FastifyInstance;
  const database: DatabaseClient = {
    db: {} as DatabaseClient['db'],
    close: vi.fn().mockResolvedValue(undefined),
    ping: vi.fn().mockResolvedValue(undefined),
  };
  const cache: RedirectCache = {
    start: vi.fn(),
    close: vi.fn().mockResolvedValue(undefined),
    get: vi.fn(),
    set: vi.fn(),
    delete: vi.fn(),
    status: vi.fn().mockReturnValue('degraded'),
  };
  const repository: RedirectStore = { findByShortCode: vi.fn(), upsert: vi.fn() };
  const source: UrlSource = { findByShortCode: vi.fn() };
  const env: Env = {
    NODE_ENV: 'test',
    URL_EVENTS_ENABLED: false,
    PORT: 3002,
    HOST: '0.0.0.0',
    LOG_LEVEL: 'fatal',
    DATABASE_URL: 'postgres://test:test@localhost:5432/test',
    REDIS_URL: 'redis://localhost:6379',
    REDIS_PASSWORD: undefined,
    URL_SERVICE_BASE_URL: 'http://url-service:3001',
    CACHE_ENABLED: true,
    CACHE_TTL_SECONDS: 3600,
    CACHE_OPERATION_TIMEOUT_MS: 50,
    UPSTREAM_TIMEOUT_MS: 500,
  };

  beforeAll(async () => {
    app = buildApp(env, { database, cache, repository, source });
    await app.ready();
  });

  afterAll(async () => app.close());

  it('reports ready while Redis is degraded', async () => {
    const response = await app.inject({ method: 'GET', url: '/health/ready' });
    expect(response.statusCode).toBe(200);
    expect(response.json().checks).toEqual({ database: 'ok', redis: 'degraded' });
  });

  it('returns 400 for an invalid short code', async () => {
    const response = await app.inject({ method: 'GET', url: `/${'x'.repeat(33)}` });
    expect(response.statusCode).toBe(400);
    expect(response.json().error.code).toBe('VALIDATION_ERROR');
  });
});
