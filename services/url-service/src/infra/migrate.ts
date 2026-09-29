import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { createDatabaseClient } from './db.js';
import { loadEnv } from '../config/env.js';

async function run(): Promise<void> {
  const env = loadEnv();
  const database = createDatabaseClient(env.DATABASE_URL);
  try {
    await migrate(database.db, { migrationsFolder: 'drizzle' });
  } finally {
    await database.close();
  }
}

run().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
