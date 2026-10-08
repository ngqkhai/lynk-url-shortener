import argon2 from 'argon2';
import { UnavailableError } from '../errors/app-error.js';
export interface PasswordHasher {
  hash(password: string): Promise<string>;
  verify(hash: string, password: string): Promise<boolean>;
  dummyHash(): Promise<string>;
}
export function createPasswordHasher(): PasswordHasher {
  let active = 0;
  const waiting: Array<() => void> = [];
  let dummy: Promise<string> | undefined;
  async function limited<T>(work: () => Promise<T>): Promise<T> {
    if (active >= 2) {
      if (waiting.length >= 16) throw new UnavailableError();
      await new Promise<void>((resolve) => waiting.push(resolve));
    } else active++;
    try {
      return await work();
    } finally {
      const next = waiting.shift();
      if (next) next();
      else active--;
    }
  }
  const hash = (password: string) =>
    limited(() =>
      argon2.hash(password, {
        type: argon2.argon2id,
        memoryCost: 19456,
        timeCost: 2,
        parallelism: 1,
      }),
    );
  return {
    hash,
    verify: (encoded, password) => limited(() => argon2.verify(encoded, password)),
    dummyHash: () =>
      (dummy ??= hash('dummy-password-for-timing-only').catch((error) => {
        dummy = undefined;
        throw error;
      })),
  };
}
