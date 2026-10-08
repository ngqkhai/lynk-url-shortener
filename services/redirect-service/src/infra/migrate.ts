import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { z } from 'zod';
import { createDatabaseClient } from './db.js';

async function run(): Promise<void> {
  const env = z.object({ DATABASE_URL: z.string().url() }).parse(process.env);
  const database = createDatabaseClient(env.DATABASE_URL, {
    connectTimeoutSeconds: z.coerce
      .number()
      .int()
      .positive()
      .default(15)
      .parse(process.env.DB_CONNECT_TIMEOUT_SECONDS),
  });
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
