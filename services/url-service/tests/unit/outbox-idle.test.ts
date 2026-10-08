import { expect, it, vi } from 'vitest';
import { OutboxDispatcher } from '../../src/services/outbox-dispatcher.service.js';
it('wakes idle reconciliation immediately and drains again after notify', async () => {
  vi.useFakeTimers();
  const claim = vi.fn().mockResolvedValue([]);
  const worker = new OutboxDispatcher(
    {
      claim,
      published: vi.fn(),
      failed: vi.fn(),
      cleanup: vi.fn(),
      hasPending: vi.fn().mockResolvedValue(false),
    },
    { publish: vi.fn(), close: vi.fn() },
    { warn: vi.fn() },
    1800000,
  );
  worker.start();
  await vi.advanceTimersByTimeAsync(0);
  expect(claim).toHaveBeenCalledTimes(1);
  worker.notify();
  await vi.advanceTimersByTimeAsync(0);
  expect(claim).toHaveBeenCalledTimes(2);
  await worker.close();
  vi.useRealTimers();
});
it('keeps retrying while a pending event is leased or awaiting backoff', async () => {
  const worker = new OutboxDispatcher(
    {
      claim: vi.fn().mockResolvedValue([]),
      published: vi.fn(),
      failed: vi.fn(),
      cleanup: vi.fn(),
      hasPending: vi.fn().mockResolvedValue(true),
    },
    { publish: vi.fn(), close: vi.fn() },
    { warn: vi.fn() },
    1800000,
  );
  expect(await worker.dispatchOnce()).toBe(true);
});
