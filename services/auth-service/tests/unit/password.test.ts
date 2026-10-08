import { describe, expect, it } from 'vitest';
import { createPasswordHasher } from '../../src/infra/password.js';
import { UnavailableError } from '../../src/errors/app-error.js';
describe('password resource bounds', () => {
  it('limits hash operations to two active and sixteen queued, with valid Argon2id output', async () => {
    const hasher = createPasswordHasher();
    const queued = Array.from({ length: 18 }, () => hasher.hash('bounded-local-password'));
    const results = await Promise.allSettled([...queued, hasher.dummyHash()]);
    expect(results.filter((r) => r.status === 'fulfilled')).toHaveLength(18);
    const rejected = results.find((r) => r.status === 'rejected');
    expect(rejected?.status === 'rejected' && rejected.reason instanceof UnavailableError).toBe(
      true,
    );
    const success = results.find((r) => r.status === 'fulfilled');
    if (success?.status !== 'fulfilled') throw new Error('Missing password hash');
    expect(success.value).toContain('$argon2id$v=19$m=19456,t=2,p=1$');
    expect(await hasher.verify(success.value, 'bounded-local-password')).toBe(true);
    expect(await hasher.verify(success.value, 'wrong-password')).toBe(false);
    // A temporary overload must not poison future unknown-email verification.
    expect(await hasher.dummyHash()).toContain('$argon2id$');
  });
});
