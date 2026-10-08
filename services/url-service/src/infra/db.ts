import { createCachedProbe } from '@lynk/shared/health';
import { drizzle, PostgresJsDatabase } from 'drizzle-orm/postgres-js';
import postgres, { Sql } from 'postgres';
import * as schema from '../models/url.model.js';
import * as outboxSchema from '../models/outbox.model.js';

const tables = { ...schema, ...outboxSchema };
export type Database = PostgresJsDatabase<typeof tables>;

export interface DatabaseClient {
  db: Database;
  close(): Promise<void>;
  ping(): Promise<void>;
  invalidateReadiness?(): void;
}

export function createDatabaseClient(
  databaseUrl: string,
  options: { readinessCacheSeconds?: number; connectTimeoutSeconds?: number } = {},
): DatabaseClient {
  const client: Sql = postgres(databaseUrl, {
    max: 10,
    connect_timeout: options.connectTimeoutSeconds ?? 2,
    idle_timeout: 60,
    connection: { statement_timeout: 5000 },
  });
  const probe = createCachedProbe(async () => {
    await client`select 1`;
  }, options.readinessCacheSeconds ?? 0);
  return {
    db: drizzle(client, { schema: tables }),
    close: () => client.end({ timeout: 5 }),
    ping: probe.ping,
    invalidateReadiness: probe.invalidate,
  };
}
