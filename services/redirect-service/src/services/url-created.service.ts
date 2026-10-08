import { urlCreatedSchema } from '@lynk/shared/events';
import type { RedirectCache } from '../infra/redis.js';
import type { RedirectStore } from '../repositories/redirect.repository.js';
import type { ServiceLogger } from './redirect.service.js';

export interface DeadLetterSink {
  send(raw: string | null, context: { partition: number; offset: string }): Promise<void>;
}

export class UrlCreatedHandler {
  constructor(
    private readonly repository: RedirectStore,
    private readonly cache: RedirectCache,
    private readonly deadLetters: DeadLetterSink,
    private readonly cacheTtlSeconds: number,
    private readonly logger: ServiceLogger,
  ) {}

  async handle(raw: string | null, context: { partition: number; offset: string }): Promise<void> {
    let input: unknown;
    try {
      input = raw === null ? null : JSON.parse(raw);
    } catch {
      input = null;
    }
    const parsed = urlCreatedSchema.safeParse(input);
    if (!parsed.success) {
      await this.deadLetters.send(raw, context);
      return;
    }
    const data = parsed.data.data;
    const record = {
      shortCode: data.shortCode,
      originalUrl: data.originalUrl,
      ownerId: data.ownerId,
      expiresAt: data.expiresAt ? new Date(data.expiresAt) : null,
    };
    // A durable read model write is required before acknowledging Kafka.
    await this.repository.upsert(record);
    const ttl = record.expiresAt
      ? Math.min(this.cacheTtlSeconds, Math.floor((record.expiresAt.getTime() - Date.now()) / 1000))
      : this.cacheTtlSeconds;
    if (ttl <= 0) return;
    try {
      await this.cache.set(record, ttl);
    } catch (error) {
      this.logger.warn({ error, shortCode: record.shortCode }, 'Event cache hydration failed');
    }
  }
}
