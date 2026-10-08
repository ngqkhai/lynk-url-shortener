import { PostgreSqlContainer, StartedPostgreSqlContainer } from '@testcontainers/postgresql';
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { FastifyInstance } from 'fastify';
import { resolve } from 'node:path';
import { GenericContainer, StartedTestContainer, Wait } from 'testcontainers';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { buildApp } from '../../src/app.js';
import { Env } from '../../src/config/env.js';
import { createDatabaseClient, DatabaseClient } from '../../src/infra/db.js';
import { RedisRedirectCache } from '../../src/infra/redis.js';
import { UrlSource } from '../../src/infra/url-source.js';
import { RedirectRepository } from '../../src/repositories/redirect.repository.js';
import { RedirectRecord } from '../../src/schemas/redirect.schema.js';

const runIntegration = process.env.RUN_INTEGRATION_TESTS === 'true';

describe.skipIf(!runIntegration)('Redirect API integration', () => {
  let postgres: StartedPostgreSqlContainer;
  let redis: StartedTestContainer;
  let database: DatabaseClient;
  let cache: RedisRedirectCache;
  let repository: RedirectRepository;
  let app: FastifyInstance;

  const active: RedirectRecord = {
    shortCode: 'HotCode',
    originalUrl: 'https://example.com/hot',
    expiresAt: null,
  };
  const source: UrlSource = {
    findByShortCode: vi.fn(async (shortCode: string) => {
      if (shortCode === active.shortCode) return active;
      if (shortCode === 'Expired') {
        return {
          shortCode,
          originalUrl: 'https://example.com/old',
          expiresAt: new Date(Date.now() - 1_000),
        };
      }
      return undefined;
    }),
  };

  beforeAll(async () => {
    [postgres, redis] = await Promise.all([
      new PostgreSqlContainer('postgres:16-alpine').start(),
      new GenericContainer('redis:8-alpine')
        .withExposedPorts(6379)
        .withWaitStrategy(Wait.forLogMessage('Ready to accept connections'))
        .start(),
    ]);
    database = createDatabaseClient(postgres.getConnectionUri());
    await migrate(database.db, { migrationsFolder: resolve(process.cwd(), 'drizzle') });
    repository = new RedirectRepository(database.db);
    cache = new RedisRedirectCache({
      enabled: true,
      url: `redis://${redis.getHost()}:${redis.getMappedPort(6379)}`,
      operationTimeoutMs: 100,
      logger: { warn: vi.fn() },
    });

    const env: Env = {
      NODE_ENV: 'test',
      URL_EVENTS_ENABLED: false,
      PORT: 3002,
      HOST: '0.0.0.0',
      LOG_LEVEL: 'fatal',
      DATABASE_URL: postgres.getConnectionUri(),
      REDIS_URL: `redis://${redis.getHost()}:${redis.getMappedPort(6379)}`,
      REDIS_PASSWORD: undefined,
      URL_SERVICE_BASE_URL: 'http://url-service:3001',
      CACHE_ENABLED: true,
      CACHE_TTL_SECONDS: 3600,
      CACHE_OPERATION_TIMEOUT_MS: 100,
      UPSTREAM_TIMEOUT_MS: 500,
    };
    app = buildApp(env, { database, repository, cache, source });
    await app.ready();
    await waitUntil(() => cache.status() === 'ready');
  }, 60_000);

  afterAll(async () => {
    await app?.close();
    await Promise.all([postgres?.stop(), redis?.stop()]);
  });

  it('lazy hydrates and serves subsequent redirects from Redis', async () => {
    const first = await app.inject({ method: 'GET', url: `/${active.shortCode}` });
    expect(first.statusCode).toBe(302);
    expect(first.headers.location).toBe(active.originalUrl);

    const second = await app.inject({ method: 'GET', url: `/${active.shortCode}` });
    expect(second.statusCode).toBe(302);
    expect(source.findByShortCode).toHaveBeenCalledTimes(1);
  });

  it('falls back to PostgreSQL when Redis is unavailable', async () => {
    await repository.upsert({
      shortCode: 'DbOnly1',
      originalUrl: 'https://example.com/db',
      expiresAt: null,
    });
    await cache.close();

    const response = await app.inject({ method: 'GET', url: '/DbOnly1' });
    expect(response.statusCode).toBe(302);
    expect(response.headers.location).toBe('https://example.com/db');
  });

  it('does not erase event ownership when an old HTTP payload arrives', async () => {
    const ownerId = 'bb47e1a7-de20-4147-bc3a-af80beedc4e1';
    await repository.upsert({
      shortCode: 'OwnerRace',
      originalUrl: 'https://example.com',
      expiresAt: null,
      ownerId,
    });
    await repository.upsert({
      shortCode: 'OwnerRace',
      originalUrl: 'https://example.com',
      expiresAt: null,
    });
    expect((await repository.findByShortCode('OwnerRace'))?.ownerId).toBe(ownerId);
  });

  it('returns 404 and 410 for missing and expired codes', async () => {
    expect((await app.inject({ method: 'GET', url: '/Missing' })).statusCode).toBe(404);
    expect((await app.inject({ method: 'GET', url: '/Expired' })).statusCode).toBe(410);
  });
});

async function waitUntil(predicate: () => boolean): Promise<void> {
  const deadline = Date.now() + 5_000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error('Timed out waiting for Redis');
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 25));
  }
}
