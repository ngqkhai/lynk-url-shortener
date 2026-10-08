import { and, eq, gt, inArray, isNull, lte, or, sql } from 'drizzle-orm';
import type { UrlCreated } from '@lynk/shared/events';
import type { Database } from '../infra/db.js';
import { urlOutbox, type OutboxRecord } from '../models/outbox.model.js';
export interface OutboxWriter {
  insert(event: UrlCreated): Promise<void>;
}
export class OutboxWriterRepository implements OutboxWriter {
  constructor(private readonly db: Pick<Database, 'insert'>) {}
  async insert(event: UrlCreated) {
    await this.db.insert(urlOutbox).values({
      eventId: event.eventId,
      topic: 'url.created',
      aggregateKey: event.data.shortCode,
      payload: event,
      createdAt: new Date(event.occurredAt),
    });
  }
}
export interface OutboxStore {
  claim(owner: string, now: Date): Promise<OutboxRecord[]>;
  published(ids: string[], owner: string, now: Date): Promise<void>;
  failed(id: string, owner: string, next: Date): Promise<void>;
  cleanup(before: Date): Promise<void>;
  hasPending?(): Promise<boolean>;
}
export class OutboxRepository implements OutboxStore {
  constructor(private readonly db: Database) {}
  async claim(owner: string, now: Date): Promise<OutboxRecord[]> {
    return this.db.transaction(async (tx) => {
      const records = await tx
        .select()
        .from(urlOutbox)
        .where(
          and(
            isNull(urlOutbox.publishedAt),
            lte(urlOutbox.nextAttemptAt, now),
            or(isNull(urlOutbox.lockedUntil), lte(urlOutbox.lockedUntil, now)),
          ),
        )
        .orderBy(urlOutbox.nextAttemptAt)
        .limit(25)
        .for('update', { skipLocked: true });
      if (!records.length) return [];
      return tx
        .update(urlOutbox)
        .set({
          lockOwner: owner,
          lockedUntil: new Date(now.getTime() + 30000),
          attempts: sql`${urlOutbox.attempts} + 1`,
        })
        .where(
          inArray(
            urlOutbox.eventId,
            records.map((r) => r.eventId),
          ),
        )
        .returning();
    });
  }
  async published(ids: string[], owner: string, now: Date) {
    if (!ids.length) return;
    await this.db
      .update(urlOutbox)
      .set({ publishedAt: now, lockedUntil: null, lockOwner: null, lastError: null })
      .where(
        and(
          inArray(urlOutbox.eventId, ids),
          eq(urlOutbox.lockOwner, owner),
          gt(urlOutbox.lockedUntil, now),
          isNull(urlOutbox.publishedAt),
        ),
      );
  }
  async failed(id: string, owner: string, next: Date) {
    await this.db
      .update(urlOutbox)
      .set({
        nextAttemptAt: next,
        lockedUntil: null,
        lockOwner: null,
        lastError: 'Publish failed; retry pending',
      })
      .where(
        and(
          eq(urlOutbox.eventId, id),
          eq(urlOutbox.lockOwner, owner),
          isNull(urlOutbox.publishedAt),
        ),
      );
  }
  async hasPending() {
    const [row] = await this.db
      .select({ eventId: urlOutbox.eventId })
      .from(urlOutbox)
      .where(isNull(urlOutbox.publishedAt))
      .limit(1);
    return Boolean(row);
  }
  async cleanup(before: Date) {
    await this.db.delete(urlOutbox).where(lte(urlOutbox.publishedAt, before));
  }
}
