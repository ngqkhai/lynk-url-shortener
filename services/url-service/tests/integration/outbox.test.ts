import { beforeAll, afterAll, describe, expect, it } from 'vitest';
import { PostgreSqlContainer, type StartedPostgreSqlContainer } from '@testcontainers/postgresql';
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { sql, eq } from 'drizzle-orm';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createDatabaseClient, type DatabaseClient } from '../../src/infra/db.js';
import { createUrlUnitOfWork } from '../../src/infra/unit-of-work.js';
import { UrlRepository } from '../../src/repositories/url.repository.js';
import { OutboxRepository } from '../../src/repositories/outbox.repository.js';
import { UrlService } from '../../src/services/url.service.js';
import { urlOutbox } from '../../src/models/outbox.model.js';
import { urls } from '../../src/models/url.model.js';
import { buildApp } from '../../src/app.js';
import { envSchema } from '../../src/config/env.js';

describe.skipIf(process.env.RUN_INTEGRATION_TESTS !== 'true')(
  'ownership and transactional outbox',
  () => {
    let container: StartedPostgreSqlContainer;
    let database: DatabaseClient;
    let service: UrlService;
    const owner = randomUUID();
    beforeAll(async () => {
      container = await new PostgreSqlContainer('postgres:16-alpine').start();
      database = createDatabaseClient(container.getConnectionUri());
      await migrate(database.db, { migrationsFolder: resolve('drizzle') });
      service = new UrlService(new UrlRepository(database.db), {
        unit: createUrlUnitOfWork(database.db),
      });
    }, 60000);
    afterAll(async () => {
      await database?.close();
      await container?.stop();
    });
    it('commits URL and validated owner event together, alias conflict has no orphan event', async () => {
      const result = await service.create(
        { originalUrl: 'https://example.com', customAlias: 'Owned01' },
        owner,
      );
      const records = await database.db.select().from(urlOutbox);
      expect(records).toHaveLength(1);
      expect(records[0].payload.data.ownerId).toBe(owner);
      expect(records[0].payload.data.urlId).toBe(result.id);
      await expect(
        service.create({ originalUrl: 'https://other.example', customAlias: 'Owned01' }, owner),
      ).rejects.toThrow();
      expect(await database.db.select().from(urlOutbox)).toHaveLength(1);
      await expect(service.getOwnedMetadata('Owned01', randomUUID())).rejects.toThrow();
      expect((await service.getOwnedMetadata('Owned01', owner)).id).toBe(result.id);
    });
    it('rolls URL back when the actual outbox insert fails', async () => {
      await database.db.execute(
        sql`alter table url_outbox add constraint reject_test_event check (aggregate_key <> 'Reject01')`,
      );
      try {
        await expect(
          service.create({ originalUrl: 'https://example.com', customAlias: 'Reject01' }, owner),
        ).rejects.toThrow();
        expect(
          await database.db.select().from(urls).where(eq(urls.shortCode, 'Reject01')),
        ).toHaveLength(0);
      } finally {
        await database.db.execute(sql`alter table url_outbox drop constraint reject_test_event`);
      }
    });
    it('two workers cannot claim the same live lease; stale worker cannot ack a reclaimed event', async () => {
      const repository = new OutboxRepository(database.db);
      const firstId = randomUUID();
      const secondId = randomUUID();
      const now = new Date();
      const claims = await Promise.all([
        repository.claim(firstId, now),
        repository.claim(secondId, now),
      ]);
      expect(claims[0].length + claims[1].length).toBe(1);
      const oldOwner = claims[0].length ? firstId : secondId;
      const record = (claims[0].length ? claims[0] : claims[1])[0];
      const newOwner = randomUUID();
      const later = new Date(now.getTime() + 31000);
      expect(await repository.claim(newOwner, later)).toHaveLength(1);
      await repository.published([record.eventId], oldOwner, later);
      expect((await database.db.select().from(urlOutbox))[0].publishedAt).toBeNull();
      await repository.published([record.eventId], newOwner, later);
      expect((await database.db.select().from(urlOutbox))[0].publishedAt).not.toBeNull();
    });
    it('enforces principal ownership in controllers and keeps legacy metadata private', async () => {
      await service.create({ originalUrl: 'https://example.com', customAlias: 'Legacy01' });
      const app = buildApp(
        envSchema.parse({
          NODE_ENV: 'test',
          DATABASE_URL: container.getConnectionUri(),
          PUBLIC_BASE_URL: 'https://lynk.test',
          JWT_PUBLIC_KEY_PATH: '/unused',
        }),
        {
          database: { ...database, close: async () => undefined },
          verify: async (header) => {
            if (header !== 'Bearer owner') throw new Error('Invalid token');
            return { userId: owner, sessionId: randomUUID(), accessId: randomUUID() };
          },
        },
      );
      try {
        expect(
          (
            await app.inject({
              method: 'POST',
              url: '/api/v1/urls',
              payload: { originalUrl: 'https://example.com' },
            })
          ).statusCode,
        ).toBe(401);
        expect(
          (
            await app.inject({
              method: 'GET',
              url: '/api/v1/urls/Owned01',
              headers: { authorization: 'Bearer owner' },
            })
          ).statusCode,
        ).toBe(200);
        expect(
          (
            await app.inject({
              method: 'GET',
              url: '/api/v1/urls/Legacy01',
              headers: { authorization: 'Bearer owner' },
            })
          ).statusCode,
        ).toBe(404);
      } finally {
        await app.close();
      }
    });
  },
);
