import { randomUUID } from 'node:crypto';
import type { OutboxStore } from '../repositories/outbox.repository.js';
import type { EventPublisher } from '../infra/kafka.js';
interface Logger {
  warn(object: unknown, message: string): void;
}
export class OutboxDispatcher {
  private running = false;
  private task?: Promise<void>;
  private wake?: () => void;
  private lastCleanup = 0;
  private notified = false;
  constructor(
    private readonly store: OutboxStore,
    private readonly publisher: EventPublisher,
    private readonly logger: Logger,
    private readonly idlePollMs = 1000,
  ) {}
  start() {
    if (this.running) return;
    this.running = true;
    this.task = this.loop();
  }
  notify() {
    this.notified = true;
    this.wake?.();
  }
  async close() {
    this.running = false;
    this.wake?.();
    await this.task;
    await this.publisher.close();
  }
  async dispatchOnce() {
    const owner = randomUUID();
    const records = await this.store.claim(owner, new Date());
    if (!records.length) return (await this.store.hasPending?.()) ?? false;
    try {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([
          this.publisher.publish(records.map((r) => r.payload)),
          new Promise<never>((_, reject) => {
            timer = setTimeout(() => reject(new Error('Publish timeout')), 10000);
          }),
        ]);
      } finally {
        clearTimeout(timer);
      }
      await this.store.published(
        records.map((r) => r.eventId),
        owner,
        new Date(),
      );
      return true;
    } catch (err) {
      this.logger.warn(
        { err, count: records.length },
        'Outbox publish failed; events remain pending',
      );
      for (const record of records)
        await this.store.failed(
          record.eventId,
          owner,
          new Date(
            Date.now() +
              Math.min(60000, 1000 * 2 ** Math.min(record.attempts - 1, 6)) +
              Math.random() * 250,
          ),
        );
      return true;
    }
  }
  private async loop() {
    while (this.running) {
      this.notified = false;
      let busy = true;
      try {
        busy = (await this.dispatchOnce()) ?? false;
        if (Date.now() - this.lastCleanup > 3600000) {
          await this.store.cleanup(new Date(Date.now() - 7 * 86400000));
          this.lastCleanup = Date.now();
        }
      } catch (err) {
        this.logger.warn({ err }, 'Outbox worker retry pending');
      }
      if (this.running && !this.notified)
        await new Promise<void>((resolve) => {
          const timer = setTimeout(
            () => {
              this.wake = undefined;
              resolve();
            },
            busy
              ? 1000
              : this.idlePollMs > 1000
                ? this.idlePollMs - (Date.now() % this.idlePollMs)
                : 1000,
          );
          this.wake = () => {
            clearTimeout(timer);
            this.wake = undefined;
            resolve();
          };
        });
    }
  }
}
