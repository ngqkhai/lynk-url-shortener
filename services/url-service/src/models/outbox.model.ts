import { pgTable, uuid, text, jsonb, timestamp, integer, index } from 'drizzle-orm/pg-core';
import { sql, type InferSelectModel } from 'drizzle-orm';
import type { UrlCreated } from '@lynk/shared/events';
export const urlOutbox = pgTable(
  'url_outbox',
  {
    eventId: uuid('event_id').primaryKey(),
    topic: text('topic').notNull(),
    aggregateKey: text('aggregate_key').notNull(),
    payload: jsonb('payload').$type<UrlCreated>().notNull(),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull(),
    publishedAt: timestamp('published_at', { withTimezone: true }),
    attempts: integer('attempts').default(0).notNull(),
    nextAttemptAt: timestamp('next_attempt_at', { withTimezone: true }).defaultNow().notNull(),
    lockedUntil: timestamp('locked_until', { withTimezone: true }),
    lockOwner: uuid('lock_owner'),
    lastError: text('last_error'),
  },
  (table) => [
    index('url_outbox_pending_idx')
      .on(table.nextAttemptAt)
      .where(sql`${table.publishedAt} is null`),
  ],
);
export type OutboxRecord = InferSelectModel<typeof urlOutbox>;
