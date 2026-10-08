import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { opaqueAccessSchema, opaqueRefreshSchema, type Principal } from '@lynk/shared/auth';
import type { AuthStore, AuthUnitOfWork } from '../repositories/auth.repository.js';
import type { PasswordHasher } from '../infra/password.js';
import type { User, Session } from '../models/auth.model.js';
import { EmailConflictError, UnauthorizedError, UnavailableError } from '../errors/app-error.js';

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  tokenType: 'Bearer';
  expiresIn: number;
}
export interface InternalSigner {
  sign(principal: Principal, expiry: Date, now: Date): Promise<string>;
}
export const hashToken = (token: string): string =>
  createHash('sha256').update(token).digest('hex');
export class AuthService {
  constructor(
    private readonly store: AuthStore,
    private readonly unit: AuthUnitOfWork,
    private readonly passwords: PasswordHasher,
    private readonly signer: InternalSigner,
    private readonly now: () => Date = () => new Date(),
  ) {}

  async register(email: string, password: string) {
    const passwordHash = await this.passwords.hash(password);
    try {
      return publicUser(await this.store.insertUser(email, passwordHash));
    } catch (error) {
      if (hasCode(error, '23505')) throw new EmailConflictError();
      throw error;
    }
  }
  async login(email: string, password: string): Promise<TokenPair> {
    const user = await this.store.findUserByEmail(email);
    const valid = await this.passwords.verify(
      user?.passwordHash ?? (await this.passwords.dummyHash()),
      password,
    );
    if (!user || !valid) throw new UnauthorizedError();
    const now = this.now();
    const session: Session = {
      id: randomUUID(),
      userId: user.id,
      createdAt: now,
      expiresAt: new Date(now.getTime() + 30 * 86400000),
      revokedAt: null,
    };
    return this.unit.run(async (store) => {
      await store.insertSession(session);
      return this.issuePair(store, session, now);
    });
  }
  async refresh(token: string): Promise<TokenPair> {
    if (!opaqueRefreshSchema.safeParse(token).success) throw new UnauthorizedError();
    const result = await this.unit.run(async (store) => {
      const initial = await store.findRefresh(hashToken(token));
      if (!initial) return undefined;
      await store.lockSession(initial.session.id);
      const current = await store.findRefresh(hashToken(token));
      const now = this.now();
      if (!current || current.session.revokedAt || current.session.expiresAt <= now)
        return undefined;
      if (current.token.consumedAt) {
        await store.revokeSession(current.session.id, now);
        return undefined;
      }
      await store.consumeRefresh(current.token.id, now);
      return this.issuePair(store, current.session, now);
    });
    // Throw after commit: a reuse revocation must survive the failed refresh.
    if (!result) throw new UnauthorizedError();
    return result;
  }
  async logout(token: string): Promise<void> {
    if (!opaqueRefreshSchema.safeParse(token).success) return;
    await this.unit.run(async (store) => {
      const found = await store.findRefresh(hashToken(token));
      if (found) {
        await store.lockSession(found.session.id);
        await store.revokeSession(found.session.id, this.now());
      }
    });
  }
  async me(userId: string) {
    const user = await this.store.findUserById(userId);
    if (!user) throw new UnauthorizedError();
    return publicUser(user);
  }
  async exchange(authorization: string | undefined): Promise<string> {
    const match = /^Bearer (at_[A-Za-z0-9_-]{43})$/i.exec(authorization ?? '');
    if (!match || !opaqueAccessSchema.safeParse(match[1]).success) throw new UnauthorizedError();
    let record;
    try {
      record = await this.store.findAccess(hashToken(match[1]));
    } catch {
      throw new UnavailableError();
    }
    const now = this.now();
    if (
      !record ||
      record.token.revokedAt ||
      record.session.revokedAt ||
      record.token.expiresAt <= now ||
      record.session.expiresAt <= now
    )
      throw new UnauthorizedError();
    const expiry = new Date(
      Math.min(
        now.getTime() + 60000,
        record.token.expiresAt.getTime(),
        record.session.expiresAt.getTime(),
      ),
    );
    if (Math.floor(expiry.getTime() / 1000) <= Math.floor(now.getTime() / 1000))
      throw new UnauthorizedError();
    return this.signer.sign(
      { userId: record.user.id, sessionId: record.session.id, accessId: record.token.id },
      expiry,
      now,
    );
  }
  private async issuePair(store: AuthStore, session: Session, now: Date): Promise<TokenPair> {
    const accessToken = `at_${randomBytes(32).toString('base64url')}`;
    const refreshToken = `rt_${randomBytes(32).toString('base64url')}`;
    const expiresAt = new Date(Math.min(now.getTime() + 900000, session.expiresAt.getTime()));
    await store.insertRefresh({
      id: randomUUID(),
      sessionId: session.id,
      tokenHash: hashToken(refreshToken),
      createdAt: now,
      consumedAt: null,
    });
    await store.insertAccess({
      id: randomUUID(),
      sessionId: session.id,
      tokenHash: hashToken(accessToken),
      createdAt: now,
      expiresAt,
      revokedAt: null,
    });
    return {
      accessToken,
      refreshToken,
      tokenType: 'Bearer',
      expiresIn: Math.floor((expiresAt.getTime() - now.getTime()) / 1000),
    };
  }
}
function publicUser(user: User) {
  return { id: user.id, email: user.email, createdAt: user.createdAt.toISOString() };
}
function hasCode(error: unknown, code: string): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    (('code' in error && error.code === code) || ('cause' in error && hasCode(error.cause, code)))
  );
}
