import { createCachedProbe } from '@lynk/shared/health';
import { drizzle, type PostgresJsDatabase } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from '../models/auth.model.js';
export type Database = PostgresJsDatabase<typeof schema>;
export interface DatabaseClient {
  db: Database;
  close(): Promise<void>;
  ping(): Promise<void>;
  invalidateReadiness?(): void;
}
export function createDatabaseClient(
  url: string,
  options: { readinessCacheSeconds?: number; connectTimeoutSeconds?: number } = {},
): DatabaseClient {
  const sql = postgres(url, {
    max: 10,
    connect_timeout: options.connectTimeoutSeconds ?? 2,
    idle_timeout: 60,
    connection: { statement_timeout: 2000 },
  });
  const probe = createCachedProbe(async () => {
    await sql`select 1`;
  }, options.readinessCacheSeconds ?? 0);
  return {
    db: drizzle(sql, { schema }),
    close: () => sql.end({ timeout: 5 }),
    ping: probe.ping,
    invalidateReadiness: probe.invalidate,
  };
}
