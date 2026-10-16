import { describe, expect, it } from 'vitest';
import { envSchema } from '../../src/config/env.js';

describe('release identity configuration', () => {
  const production = {
    NODE_ENV: 'production',
    DATABASE_URL: 'postgres://lynk:secret@localhost:5432/lynk',
    REDIS_URL: 'redis://localhost:6379',
    URL_SERVICE_BASE_URL: 'http://url-service:3001',
  };

  it('requires an immutable source SHA in production', () => {
    expect(envSchema.safeParse({ ...production, RELEASE_SHA: 'local' }).success).toBe(false);
    expect(envSchema.safeParse({ ...production, RELEASE_SHA: 'a'.repeat(40) }).success).toBe(true);
  });
});
