import type { Database } from './db.js';
import { UrlRepository, type UrlStore } from '../repositories/url.repository.js';
import { OutboxWriterRepository, type OutboxWriter } from '../repositories/outbox.repository.js';
export interface UrlUnitOfWork {
  run<T>(work: (urls: UrlStore, outbox: OutboxWriter) => Promise<T>): Promise<T>;
}
export function createUrlUnitOfWork(db: Database): UrlUnitOfWork {
  return {
    run: (work) =>
      db.transaction((tx) => work(new UrlRepository(tx), new OutboxWriterRepository(tx))),
  };
}
