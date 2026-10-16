import { describe, expect, it } from 'vitest';
import { envSchema } from '../../src/config/env.js';

describe('release identity configuration', () => {
  const production = {
    NODE_ENV: 'production',
    DATABASE_URL: 'postgres://lynk:secret@localhost:5432/lynk',
    PUBLIC_BASE_URL: 'https://lynk.codes',
    JWT_PUBLIC_KEY_PATH: '/keys/jwt-public.pem',
  };

  it('accepts a local build identity and an immutable source SHA', () => {
    expect(envSchema.safeParse({ ...production, RELEASE_SHA: 'local' }).success).toBe(true);
    expect(envSchema.safeParse({ ...production, RELEASE_SHA: 'a'.repeat(40) }).success).toBe(true);
  });
});
