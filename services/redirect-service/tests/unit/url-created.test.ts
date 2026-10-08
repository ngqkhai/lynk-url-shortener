import { randomUUID } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import { UrlCreatedHandler } from '../../src/services/url-created.service.js';
import type { RedirectCache } from '../../src/infra/redis.js';
import { parseRedirectRecord } from '../../src/schemas/redirect.schema.js';
const event = () => ({
  eventId: randomUUID(),
  eventType: 'url.created',
  schemaVersion: 1,
  occurredAt: new Date().toISOString(),
  data: {
    urlId: randomUUID(),
    shortCode: 'Test123',
    originalUrl: 'https://example.com',
    createdAt: new Date().toISOString(),
    expiresAt: null,
    ownerId: randomUUID(),
  },
});
const context = { partition: 0, offset: '1' };
describe('URL event delivery', () => {
  function setup() {
    const upsert = vi.fn().mockResolvedValue(undefined);
    const set = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);
    const handler = new UrlCreatedHandler(
      { upsert, findByShortCode: vi.fn() },
      { set } as unknown as RedirectCache,
      { send },
      3600,
      { warn: vi.fn() },
    );
    return { upsert, set, send, handler };
  }
  it('persists before cache and tolerates Redis failure', async () => {
    const { upsert, set, handler } = setup();
    set.mockRejectedValue(new Error('redis down'));
    await handler.handle(JSON.stringify(event()), context);
    expect(upsert.mock.invocationCallOrder[0]).toBeLessThan(set.mock.invocationCallOrder[0]);
  });
  it('rejects DB and DLQ failures so offsets cannot advance', async () => {
    const { upsert, set, send, handler } = setup();
    upsert.mockRejectedValue(new Error('db down'));
    await expect(handler.handle(JSON.stringify(event()), context)).rejects.toThrow('db down');
    expect(set).not.toHaveBeenCalled();
    send.mockRejectedValue(new Error('broker down'));
    await expect(handler.handle('invalid json', context)).rejects.toThrow('broker down');
  });
  it('routes invalid schema to DLQ and persists expired events without caching', async () => {
    const { upsert, set, send, handler } = setup();
    await handler.handle(JSON.stringify({ schemaVersion: 2 }), context);
    expect(send).toHaveBeenCalledTimes(1);
    expect(upsert).not.toHaveBeenCalled();
    const expired = event();
    expired.data.expiresAt = new Date(Date.now() - 1000).toISOString() as never;
    await handler.handle(JSON.stringify(expired), context);
    expect(upsert).toHaveBeenCalledTimes(1);
    expect(set).not.toHaveBeenCalled();
  });
  it('accepts old Redis and HTTP records as unowned', () => {
    expect(
      parseRedirectRecord({ shortCode: 'Old', originalUrl: 'https://example.com', expiresAt: null })
        .ownerId,
    ).toBeNull();
  });
});
