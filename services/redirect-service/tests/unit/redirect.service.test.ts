import { describe, expect, it, vi } from 'vitest';
import {
  DependencyUnavailableError,
  ExpiredError,
  NotFoundError,
} from '../../src/errors/app-error.js';
import { RedirectCache } from '../../src/infra/redis.js';
import { UrlSource } from '../../src/infra/url-source.js';
import { RedirectStore } from '../../src/repositories/redirect.repository.js';
import { RedirectRecord } from '../../src/schemas/redirect.schema.js';
import { RedirectService } from '../../src/services/redirect.service.js';

const active: RedirectRecord = {
  shortCode: 'Active1',
  originalUrl: 'https://example.com',
  expiresAt: new Date(Date.now() + 30_000),
};

function dependencies() {
  const repository: RedirectStore = {
    findByShortCode: vi.fn().mockResolvedValue(undefined),
    upsert: vi.fn().mockResolvedValue(undefined),
  };
  const cache: RedirectCache = {
    start: vi.fn(),
    close: vi.fn().mockResolvedValue(undefined),
    get: vi.fn().mockResolvedValue(undefined),
    set: vi.fn().mockResolvedValue(undefined),
    delete: vi.fn().mockResolvedValue(undefined),
    status: vi.fn().mockReturnValue('ready'),
  };
  const source: UrlSource = { findByShortCode: vi.fn().mockResolvedValue(undefined) };
  const logger = { warn: vi.fn() };
  return { repository, cache, source, logger };
}

describe('RedirectService', () => {
  it('returns a cache hit without reading the database or source', async () => {
    const deps = dependencies();
    vi.mocked(deps.cache.get).mockResolvedValue(active);
    const service = createService(deps);

    await expect(service.resolve(active.shortCode)).resolves.toEqual(active);
    expect(deps.repository.findByShortCode).not.toHaveBeenCalled();
    expect(deps.source.findByShortCode).not.toHaveBeenCalled();
  });

  it('falls back to the database when Redis fails', async () => {
    const deps = dependencies();
    vi.mocked(deps.cache.get).mockRejectedValue(new Error('redis down'));
    vi.mocked(deps.repository.findByShortCode).mockResolvedValue(active);

    await expect(createService(deps).resolve(active.shortCode)).resolves.toEqual(active);
    expect(deps.logger.warn).toHaveBeenCalled();
    expect(deps.source.findByShortCode).not.toHaveBeenCalled();
  });

  it('hydrates the read model and cache from URL Service', async () => {
    const deps = dependencies();
    vi.mocked(deps.source.findByShortCode).mockResolvedValue(active);

    await expect(createService(deps).resolve(active.shortCode)).resolves.toEqual(active);
    expect(deps.repository.upsert).toHaveBeenCalledWith(active);
    expect(deps.cache.set).toHaveBeenCalledWith(active, expect.any(Number));
    expect(vi.mocked(deps.cache.set).mock.calls[0][1]).toBeLessThanOrEqual(30);
  });

  it('uses the URL source when the read database fails', async () => {
    const deps = dependencies();
    vi.mocked(deps.repository.findByShortCode).mockRejectedValue(new Error('db down'));
    vi.mocked(deps.source.findByShortCode).mockResolvedValue(active);

    await expect(createService(deps).resolve(active.shortCode)).resolves.toEqual(active);
  });

  it('returns 404 for a code absent from every source', async () => {
    const deps = dependencies();
    await expect(createService(deps).resolve('Missing')).rejects.toBeInstanceOf(NotFoundError);
  });

  it('returns 410 and evicts an expired cache entry', async () => {
    const deps = dependencies();
    vi.mocked(deps.cache.get).mockResolvedValue({ ...active, expiresAt: new Date(Date.now() - 1) });

    await expect(createService(deps).resolve(active.shortCode)).rejects.toBeInstanceOf(
      ExpiredError,
    );
    expect(deps.cache.delete).toHaveBeenCalledWith(active.shortCode);
  });

  it('propagates 503 when every local source misses and URL Service is unavailable', async () => {
    const deps = dependencies();
    vi.mocked(deps.source.findByShortCode).mockRejectedValue(new DependencyUnavailableError());

    await expect(createService(deps).resolve('Unavailable')).rejects.toBeInstanceOf(
      DependencyUnavailableError,
    );
  });
});

function createService(deps: ReturnType<typeof dependencies>): RedirectService {
  return new RedirectService(deps.repository, deps.cache, deps.source, 3600, deps.logger);
}
