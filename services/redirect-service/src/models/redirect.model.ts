import { InferInsertModel, InferSelectModel } from 'drizzle-orm';
import { pgTable, text, timestamp, uuid } from 'drizzle-orm/pg-core';

export const redirectUrls = pgTable('redirect_urls', {
  shortCode: text('short_code').primaryKey(),
  originalUrl: text('original_url').notNull(),
  expiresAt: timestamp('expires_at', { withTimezone: true }),
  ownerId: uuid('owner_id'),
  syncedAt: timestamp('synced_at', { withTimezone: true }).defaultNow().notNull(),
});

export type RedirectUrl = InferSelectModel<typeof redirectUrls>;
export type NewRedirectUrl = InferInsertModel<typeof redirectUrls>;
