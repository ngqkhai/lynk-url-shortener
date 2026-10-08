import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { PostgreSqlContainer, StartedPostgreSqlContainer } from '@testcontainers/postgresql';
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { sql } from 'drizzle-orm';
import { resolve } from 'node:path';
import { FastifyInstance } from 'fastify';
import { buildApp } from '../../src/app.js';
import { Env } from '../../src/config/env.js';
import { createDatabaseClient, DatabaseClient } from '../../src/infra/db.js';

const runIntegration = process.env.RUN_INTEGRATION_TESTS === 'true';

describe.skipIf(!runIntegration)('URL API integration', () => {
  let container: StartedPostgreSqlContainer;
  let database: DatabaseClient;
  let app: FastifyInstance;

  beforeAll(async () => {
    container = await new PostgreSqlContainer('postgres:16-alpine').start();
    database = createDatabaseClient(container.getConnectionUri());
    await migrate(database.db, { migrationsFolder: resolve(process.cwd(), 'drizzle') });
    const env: Env = {
      NODE_ENV: 'test',
      AUTH_REQUIRED: false,
      URL_EVENTS_ENABLED: false,
      PORT: 3001,
      HOST: '0.0.0.0',
      LOG_LEVEL: 'fatal',
      DATABASE_URL: container.getConnectionUri(),
      PUBLIC_BASE_URL: 'https://lynk.test',
    };
    app = buildApp(env, { database });
    await app.ready();
  }, 60_000);

  afterAll(async () => {
    await app?.close();
    await container?.stop();
  });

  it('creates and retrieves a URL through public and internal metadata APIs', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/v1/urls',
      payload: { originalUrl: 'https://example.com/destination', customAlias: 'DemoLink' },
    });
    expect(created.statusCode).toBe(201);
    expect(created.json().shortUrl).toBe('https://lynk.test/DemoLink');

    const metadata = await app.inject({ method: 'GET', url: '/api/v1/urls/DemoLink' });
    expect(metadata.statusCode).toBe(200);
    expect(metadata.json().originalUrl).toBe('https://example.com/destination');

    const internal = await app.inject({ method: 'GET', url: '/internal/urls/DemoLink' });
    expect(internal.statusCode).toBe(200);
    expect(internal.json()).toEqual({
      shortCode: 'DemoLink',
      originalUrl: 'https://example.com/destination',
      expiresAt: null,
      ownerId: null,
    });
  });

  it('returns conflict and not found appropriately', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/v1/urls',
      payload: { originalUrl: 'https://example.com', customAlias: 'Taken01' },
    });
    const duplicate = await app.inject({
      method: 'POST',
      url: '/api/v1/urls',
      payload: { originalUrl: 'https://example.org', customAlias: 'Taken01' },
    });
    expect(duplicate.statusCode).toBe(409);

    await database.db.execute(
      sql`insert into urls (short_code, original_url, expires_at) values ('OldLink', 'https://example.com', now() - interval '1 day')`,
    );
    expect((await app.inject({ method: 'GET', url: '/internal/urls/OldLink' })).statusCode).toBe(
      200,
    );
    expect((await app.inject({ method: 'GET', url: '/internal/urls/Missing' })).statusCode).toBe(
      404,
    );
  });
});
