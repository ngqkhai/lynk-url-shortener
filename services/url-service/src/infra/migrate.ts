import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { createDatabaseClient } from './db.js';
import { z } from 'zod';

async function run(): Promise<void> {
  const database = createDatabaseClient(z.string().url().parse(process.env.DATABASE_URL), {
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
