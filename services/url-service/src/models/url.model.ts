import { InferInsertModel, InferSelectModel } from 'drizzle-orm';
import { pgTable, text, timestamp, uuid } from 'drizzle-orm/pg-core';

export const urls = pgTable('urls', {
  id: uuid('id').defaultRandom().primaryKey(),
  shortCode: text('short_code').notNull().unique(),
  originalUrl: text('original_url').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
  expiresAt: timestamp('expires_at', { withTimezone: true }),
  ownerId: uuid('owner_id'),
});

export type Url = InferSelectModel<typeof urls>;
export type NewUrl = InferInsertModel<typeof urls>;
