/** Cache dependency probes only. Authorization and business queries never use this cache. */
export function createCachedProbe(work: () => Promise<void>, cacheSeconds: number, now = Date.now) {
  let validUntil = 0;
  let pending: Promise<void> | undefined;
  return {
    invalidate() {
      validUntil = 0;
    },
    async ping() {
      if (cacheSeconds > 0 && now() < validUntil) return;
      if (!pending)
        pending = work()
          .then(() => {
            const window = cacheSeconds * 1000;
            // Align replicas to one wall-clock bucket so probes do not keep Neon warm in staggered phases.
            validUntil = window > 0 ? (Math.floor(now() / window) + 1) * window : now();
          })
          .finally(() => {
            pending = undefined;
          });
      await pending;
    },
  };
}
