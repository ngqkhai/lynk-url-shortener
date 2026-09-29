import { ExpiredError, NotFoundError } from '../errors/app-error.js';
import { RedirectCache } from '../infra/redis.js';
import { UrlSource } from '../infra/url-source.js';
import { RedirectStore } from '../repositories/redirect.repository.js';
import { RedirectRecord } from '../schemas/redirect.schema.js';

export interface ServiceLogger {
  warn(object: unknown, message?: string): void;
}

export class RedirectService {
  constructor(
    private readonly repository: RedirectStore,
    private readonly cache: RedirectCache,
    private readonly source: UrlSource,
    private readonly cacheTtlSeconds: number,
    private readonly logger: ServiceLogger,
  ) {}

  async resolve(shortCode: string): Promise<RedirectRecord> {
    const cached = await this.readCache(shortCode);
    if (cached) return this.requireActive(cached);

    const stored = await this.readDatabase(shortCode);
    if (stored) {
      const active = this.requireActive(stored);
      await this.writeCache(active);
      return active;
    }

    const sourceRecord = await this.source.findByShortCode(shortCode);
    if (!sourceRecord) throw new NotFoundError();
    const active = this.requireActive(sourceRecord);

    await Promise.allSettled([this.persist(active), this.writeCache(active)]);
    return active;
  }

  private async readCache(shortCode: string): Promise<RedirectRecord | undefined> {
    try {
      return await this.cache.get(shortCode);
    } catch (error) {
      this.logger.warn({ error, shortCode }, 'Cache read failed; falling back to database');
      return undefined;
    }
  }

  private async readDatabase(shortCode: string): Promise<RedirectRecord | undefined> {
    try {
      return await this.repository.findByShortCode(shortCode);
    } catch (error) {
      this.logger.warn({ error, shortCode }, 'Redirect database read failed; using URL source');
      return undefined;
    }
  }

  private async persist(record: RedirectRecord): Promise<void> {
    try {
      await this.repository.upsert(record);
    } catch (error) {
      this.logger.warn({ error, shortCode: record.shortCode }, 'Read model hydration failed');
    }
  }

  private async writeCache(record: RedirectRecord): Promise<void> {
    const ttl = this.ttlFor(record);
    if (ttl <= 0) return;
    try {
      await this.cache.set(record, ttl);
    } catch (error) {
      this.logger.warn({ error, shortCode: record.shortCode }, 'Cache write failed');
    }
  }

  private requireActive(record: RedirectRecord): RedirectRecord {
    if (record.expiresAt && record.expiresAt <= new Date()) {
      void this.cache.delete(record.shortCode).catch(() => undefined);
      throw new ExpiredError();
    }
    return record;
  }

  private ttlFor(record: RedirectRecord): number {
    if (!record.expiresAt) return this.cacheTtlSeconds;
    const remaining = Math.ceil((record.expiresAt.getTime() - Date.now()) / 1_000);
    return Math.min(this.cacheTtlSeconds, Math.max(0, remaining));
  }
}
