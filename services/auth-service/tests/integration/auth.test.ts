import { beforeAll, afterAll, describe, expect, it } from 'vitest';
import { PostgreSqlContainer, type StartedPostgreSqlContainer } from '@testcontainers/postgresql';
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { resolve } from 'node:path';
import { generateKeyPair, exportPKCS8, exportSPKI, decodeJwt } from 'jose';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { buildApp, type AuthApp } from '../../src/app.js';
import { envSchema } from '../../src/config/env.js';
import { createDatabaseClient, type DatabaseClient } from '../../src/infra/db.js';
import { accessTokens, refreshTokens } from '../../src/models/auth.model.js';

const enabled = process.env.RUN_INTEGRATION_TESTS === 'true';
describe.skipIf(!enabled)('auth transactions and HTTP', () => {
  let container: StartedPostgreSqlContainer;
  let database: DatabaseClient;
  let app: AuthApp;
  let directory: string;
  let clock = new Date();
  let pair: { accessToken: string; refreshToken: string };
  beforeAll(async () => {
    container = await new PostgreSqlContainer('postgres:16-alpine').start();
    database = createDatabaseClient(container.getConnectionUri());
    await migrate(database.db, { migrationsFolder: resolve('drizzle') });
    const keys = await generateKeyPair('RS256', { extractable: true });
    directory = mkdtempSync(`${tmpdir()}/lynk-auth-test-`);
    writeFileSync(`${directory}/private.pem`, await exportPKCS8(keys.privateKey), { mode: 0o600 });
    writeFileSync(`${directory}/public.pem`, await exportSPKI(keys.publicKey));
    app = await buildApp(
      envSchema.parse({
        NODE_ENV: 'test',
        DATABASE_URL: container.getConnectionUri(),
        JWT_PRIVATE_KEY_PATH: `${directory}/private.pem`,
        JWT_PUBLIC_KEY_PATH: `${directory}/public.pem`,
      }),
      { database, now: () => clock },
    );
    await app.ready();
  }, 60000);
  afterAll(async () => {
    await app?.close();
    await container?.stop();
    if (directory) rmSync(directory, { recursive: true });
  });
  const credentials = { email: ' Owner@Example.com ', password: 'long-local-password' };
  it('normalizes email, hashes password, returns opaque tokens and stores token hashes only', async () => {
    expect(
      (await app.inject({ method: 'POST', url: '/api/v1/auth/register', payload: credentials }))
        .statusCode,
    ).toBe(201);
    expect(
      (await app.inject({ method: 'POST', url: '/api/v1/auth/register', payload: credentials }))
        .statusCode,
    ).toBe(409);
    expect(
      (
        await app.inject({
          method: 'POST',
          url: '/api/v1/auth/login',
          payload: { ...credentials, password: 'wrong-password-here' },
        })
      ).statusCode,
    ).toBe(401);
    const login = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: credentials,
    });
    expect(login.statusCode).toBe(200);
    pair = login.json();
    expect(pair.accessToken).toMatch(/^at_[A-Za-z0-9_-]{43}$/);
    expect(pair.refreshToken).toMatch(/^rt_[A-Za-z0-9_-]{43}$/);
    const stored = await database.db.select().from(accessTokens);
    const refresh = await database.db.select().from(refreshTokens);
    expect(stored[0].tokenHash).toMatch(/^[a-f0-9]{64}$/);
    expect(refresh[0].tokenHash).not.toBe(pair.refreshToken);
    const jwt = await app.authService.exchange(`Bearer ${pair.accessToken}`);
    const claims = decodeJwt(jwt);
    expect(claims.exp! - claims.iat!).toBeLessThanOrEqual(60);
    const me = await app.inject({
      method: 'GET',
      url: '/api/v1/auth/me',
      headers: { authorization: `Bearer ${jwt}` },
    });
    expect(me.json().user.email).toBe('owner@example.com');
    expect(
      (
        await app.inject({
          method: 'GET',
          url: '/internal/auth/forward',
          headers: { authorization: `Bearer ${pair.accessToken}` },
        })
      ).statusCode,
    ).toBe(404);
    await expect(app.authService.exchange(`Bearer ${jwt}`)).rejects.toThrow();
  });
  it('serializes concurrent rotation and commits family revocation on reuse', async () => {
    const results = await Promise.allSettled([
      app.authService.refresh(pair.refreshToken),
      app.authService.refresh(pair.refreshToken),
    ]);
    expect(results.filter((result) => result.status === 'fulfilled')).toHaveLength(1);
    const winner = results.find((result) => result.status === 'fulfilled');
    if (winner?.status !== 'fulfilled') throw new Error('Missing successful rotation');
    await expect(app.authService.exchange(`Bearer ${pair.accessToken}`)).rejects.toThrow();
    await expect(app.authService.exchange(`Bearer ${winner.value.accessToken}`)).rejects.toThrow();
    await expect(app.authService.refresh(winner.value.refreshToken)).rejects.toThrow();
  });
  it('normal rotation preserves old access but logout revokes both pairs', async () => {
    const first = await app.authService.login('owner@example.com', credentials.password);
    const second = await app.authService.refresh(first.refreshToken);
    await expect(app.authService.exchange(`Bearer ${first.accessToken}`)).resolves.toEqual(
      expect.any(String),
    );
    await app.authService.logout(first.refreshToken);
    await expect(app.authService.exchange(`Bearer ${second.accessToken}`)).rejects.toThrow();
    await app.authService.logout(first.refreshToken);
  });
  it('rejects unknown, expired access and expired refresh families', async () => {
    await expect(app.authService.exchange(`Bearer at_${'a'.repeat(43)}`)).rejects.toThrow();
    const pair = await app.authService.login('owner@example.com', credentials.password);
    clock = new Date(clock.getTime() + 901000);
    await expect(app.authService.exchange(`Bearer ${pair.accessToken}`)).rejects.toThrow();
    clock = new Date(clock.getTime() + 30 * 86400000);
    await expect(app.authService.refresh(pair.refreshToken)).rejects.toThrow();
  });
});
