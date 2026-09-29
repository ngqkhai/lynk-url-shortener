import { drizzle, PostgresJsDatabase } from 'drizzle-orm/postgres-js';
import postgres, { Sql } from 'postgres';
import * as schema from '../models/url.model.js';

export type Database = PostgresJsDatabase<typeof schema>;

export interface DatabaseClient {
  db: Database;
  close(): Promise<void>;
  ping(): Promise<void>;
}

export function createDatabaseClient(databaseUrl: string): DatabaseClient {
  const client: Sql = postgres(databaseUrl, { max: 10 });
  return {
    db: drizzle(client, { schema }),
    close: () => client.end({ timeout: 5 }),
    ping: async () => {
      await client`select 1`;
    },
  };
}
