import { eq } from 'drizzle-orm';
import { Database } from '../infra/db.js';
import { redirectUrls } from '../models/redirect.model.js';
import { RedirectRecord } from '../schemas/redirect.schema.js';

export interface RedirectStore {
  findByShortCode(shortCode: string): Promise<RedirectRecord | undefined>;
  upsert(record: RedirectRecord): Promise<void>;
}

export class RedirectRepository implements RedirectStore {
  constructor(private readonly db: Database) {}

  async findByShortCode(shortCode: string): Promise<RedirectRecord | undefined> {
    const [record] = await this.db
      .select()
      .from(redirectUrls)
      .where(eq(redirectUrls.shortCode, shortCode))
      .limit(1);
    return record;
  }

  async upsert(record: RedirectRecord): Promise<void> {
    await this.db
      .insert(redirectUrls)
      .values({ ...record, syncedAt: new Date() })
      .onConflictDoUpdate({
        target: redirectUrls.shortCode,
        set: {
          originalUrl: record.originalUrl,
          expiresAt: record.expiresAt,
          syncedAt: new Date(),
        },
      });
  }
}
