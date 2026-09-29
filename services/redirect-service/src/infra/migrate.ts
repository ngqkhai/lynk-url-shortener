import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { loadEnv } from '../config/env.js';
import { createDatabaseClient } from './db.js';

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
