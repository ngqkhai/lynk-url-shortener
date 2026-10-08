import { expect, it, vi } from 'vitest';
import { createCachedProbe } from '../src/health.js';
it('bounds probe caching and rechecks after invalidation or expiry', async () => {
  let now = 1000;
  const work = vi.fn().mockResolvedValue(undefined);
  const probe = createCachedProbe(work, 900, () => now);
  await Promise.all([probe.ping(), probe.ping()]);
  await probe.ping();
  expect(work).toHaveBeenCalledTimes(1);
  probe.invalidate();
  await probe.ping();
  expect(work).toHaveBeenCalledTimes(2);
  now += 901000;
  await probe.ping();
  expect(work).toHaveBeenCalledTimes(3);
});
it('failed probes are never cached as healthy', async () => {
  const work = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValue(undefined);
  const probe = createCachedProbe(work, 900);
  await expect(probe.ping()).rejects.toThrow('down');
  await probe.ping();
  expect(work).toHaveBeenCalledTimes(2);
});
it('aligns separate services to the same probe bucket after staggered startup', async () => {
  let now = 1000;
  const first = vi.fn().mockResolvedValue(undefined),
    second = vi.fn().mockResolvedValue(undefined);
  const a = createCachedProbe(first, 900, () => now),
    b = createCachedProbe(second, 900, () => now);
  await a.ping();
  now = 300000;
  await b.ping();
  now = 900000;
  await a.ping();
  await b.ping();
  expect(first).toHaveBeenCalledTimes(2);
  expect(second).toHaveBeenCalledTimes(2);
});
