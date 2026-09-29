import { createClient, RedisClientType } from 'redis';
import { RedirectRecord, parseRedirectRecord } from '../schemas/redirect.schema.js';

export type CacheStatus = 'ready' | 'degraded' | 'disabled';

export interface RedirectCache {
  start(): void;
  close(): Promise<void>;
  get(shortCode: string): Promise<RedirectRecord | undefined>;
  set(record: RedirectRecord, ttlSeconds: number): Promise<void>;
  delete(shortCode: string): Promise<void>;
  status(): CacheStatus;
}

export interface CacheLogger {
  warn(object: unknown, message?: string): void;
}

export interface RedisCacheOptions {
  enabled: boolean;
  url: string;
  password?: string;
  operationTimeoutMs: number;
  logger: CacheLogger;
}

export class RedisRedirectCache implements RedirectCache {
  private readonly client: RedisClientType;

  constructor(private readonly options: RedisCacheOptions) {
    this.client = createClient({
      url: options.url,
      password: options.password,
      disableOfflineQueue: true,
      socket: {
        connectTimeout: 500,
        reconnectStrategy: (retries) => Math.min(50 * 2 ** retries, 1_000),
      },
    });
    this.client.on('error', (error) => options.logger.warn({ error }, 'Redis client error'));
  }

  start(): void {
    if (!this.options.enabled || this.client.isOpen) return;
    void this.client
      .connect()
      .catch((error: unknown) => this.options.logger.warn({ error }, 'Redis unavailable'));
  }

  async close(): Promise<void> {
    if (!this.client.isOpen) return;
    try {
      await this.client.quit();
    } catch {
      this.client.destroy();
    }
  }

  async get(shortCode: string): Promise<RedirectRecord | undefined> {
    if (!this.options.enabled) return undefined;
    const payload = await this.run(() => this.client.get(this.key(shortCode)));
    if (!payload) return undefined;
    try {
      return parseRedirectRecord(JSON.parse(payload));
    } catch (error) {
      this.options.logger.warn({ error, shortCode }, 'Discarding invalid Redis payload');
      await this.delete(shortCode).catch(() => undefined);
      return undefined;
    }
  }

  async set(record: RedirectRecord, ttlSeconds: number): Promise<void> {
    if (!this.options.enabled) return;
    const payload = JSON.stringify({
      ...record,
      expiresAt: record.expiresAt?.toISOString() ?? null,
    });
    await this.run(() => this.client.set(this.key(record.shortCode), payload, { EX: ttlSeconds }));
  }

  async delete(shortCode: string): Promise<void> {
    if (!this.options.enabled) return;
    await this.run(() => this.client.del(this.key(shortCode)));
  }

  status(): CacheStatus {
    if (!this.options.enabled) return 'disabled';
    return this.client.isReady ? 'ready' : 'degraded';
  }

  private key(shortCode: string): string {
    return `redirect:v1:${shortCode}`;
  }

  private async run<T>(operation: () => Promise<T>): Promise<T> {
    if (!this.client.isReady) throw new Error('Redis is not ready');
    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(
        () => reject(new Error('Redis operation timed out')),
        this.options.operationTimeoutMs,
      );
      timeout.unref();
      operation().then(
        (value) => {
          clearTimeout(timeout);
          resolve(value);
        },
        (error: unknown) => {
          clearTimeout(timeout);
          reject(error);
        },
      );
    });
  }
}
