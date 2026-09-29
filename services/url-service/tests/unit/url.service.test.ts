import { describe, expect, it, vi } from 'vitest';
import { ConflictError } from '../../src/errors/app-error.js';
import { UrlRepository } from '../../src/repositories/url.repository.js';
import { UrlService } from '../../src/services/url.service.js';

const input = { originalUrl: 'https://example.com' };

describe('UrlService', () => {
  it('retries generated codes after a database unique violation', async () => {
    const create = vi.fn().mockRejectedValueOnce({ code: '23505' }).mockResolvedValueOnce({
      id: 'id',
      shortCode: 'second1',
      originalUrl: input.originalUrl,
      createdAt: new Date(),
      expiresAt: null,
    });
    const service = new UrlService({ create } as unknown as UrlRepository, {
      generateCode: vi.fn().mockReturnValueOnce('first01').mockReturnValueOnce('second1'),
    });

    const result = await service.create(input);

    expect(result.shortCode).toBe('second1');
    expect(create).toHaveBeenCalledTimes(2);
  });

  it('returns conflict for an existing custom alias', async () => {
    const create = vi.fn().mockRejectedValue({ code: '23505' });
    const service = new UrlService({ create } as unknown as UrlRepository);

    await expect(service.create({ ...input, customAlias: 'MyLink' })).rejects.toBeInstanceOf(
      ConflictError,
    );
  });
});
