import { describe, expect, it } from 'vitest';
import { createUrlSchema } from '../../src/schemas/url.schema.js';

describe('createUrlSchema', () => {
  it('accepts future HTTP(S) URLs and a case-sensitive alias', () => {
    const result = createUrlSchema.safeParse({
      originalUrl: 'https://example.com/path',
      customAlias: 'MyLink',
      expiresAt: '2030-01-01T00:00:00.000Z',
    });
    expect(result.success).toBe(true);
  });

  it('rejects non-HTTP schemes, reserved aliases, and past expiry', () => {
    expect(createUrlSchema.safeParse({ originalUrl: 'mailto:user@example.com' }).success).toBe(
      false,
    );
    expect(
      createUrlSchema.safeParse({ originalUrl: 'https://example.com', customAlias: 'api' }).success,
    ).toBe(false);
    expect(
      createUrlSchema.safeParse({
        originalUrl: 'https://example.com',
        expiresAt: '2020-01-01T00:00:00.000Z',
      }).success,
    ).toBe(false);
  });
});
