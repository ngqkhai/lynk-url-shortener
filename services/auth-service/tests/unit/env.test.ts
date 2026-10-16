import { describe, expect, it } from 'vitest';
import { envSchema } from '../../src/config/env.js';

describe('release identity configuration', () => {
  const production = {
    NODE_ENV: 'production',
    DATABASE_URL: 'postgres://lynk:secret@localhost:5432/lynk',
    JWT_PRIVATE_KEY_PATH: '/keys/jwt-private.pem',
    JWT_PUBLIC_KEY_PATH: '/keys/jwt-public.pem',
  };

  it('requires an immutable source SHA in production', () => {
    expect(envSchema.safeParse({ ...production, RELEASE_SHA: 'local' }).success).toBe(false);
    expect(envSchema.safeParse({ ...production, RELEASE_SHA: 'a'.repeat(40) }).success).toBe(true);
  });
});
