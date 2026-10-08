import { eq, lte } from 'drizzle-orm';
import type { Database } from '../infra/db.js';
import {
  users,
  refreshSessions,
  refreshTokens,
  accessTokens,
  type User,
  type Session,
  type RefreshToken,
  type AccessToken,
} from '../models/auth.model.js';

export interface AuthStore {
  findUserByEmail(email: string): Promise<User | undefined>;
  findUserById(id: string): Promise<User | undefined>;
  insertUser(email: string, passwordHash: string): Promise<User>;
  insertSession(session: Session): Promise<void>;
  insertRefresh(token: RefreshToken): Promise<void>;
  insertAccess(token: AccessToken): Promise<void>;
  findRefresh(hash: string): Promise<{ token: RefreshToken; session: Session } | undefined>;
  findAccess(
    hash: string,
  ): Promise<{ token: AccessToken; session: Session; user: User } | undefined>;
  lockSession(id: string): Promise<void>;
  consumeRefresh(id: string, at: Date): Promise<void>;
  revokeSession(id: string, at: Date): Promise<void>;
  cleanup(now: Date): Promise<void>;
}
export interface AuthUnitOfWork {
  run<T>(work: (store: AuthStore) => Promise<T>): Promise<T>;
}
type QueryDatabase = Pick<Database, 'select' | 'insert' | 'update' | 'delete'>;
export class AuthRepository implements AuthStore {
  constructor(private readonly db: QueryDatabase) {}
  async findUserByEmail(email: string) {
    return (await this.db.select().from(users).where(eq(users.email, email)).limit(1))[0];
  }
  async findUserById(id: string) {
    return (await this.db.select().from(users).where(eq(users.id, id)).limit(1))[0];
  }
  async insertUser(email: string, passwordHash: string) {
    return (await this.db.insert(users).values({ email, passwordHash }).returning())[0];
  }
  async insertSession(session: Session) {
    await this.db.insert(refreshSessions).values(session);
  }
  async insertRefresh(token: RefreshToken) {
    await this.db.insert(refreshTokens).values(token);
  }
  async insertAccess(token: AccessToken) {
    await this.db.insert(accessTokens).values(token);
  }
  async findRefresh(hash: string) {
    return (
      await this.db
        .select({ token: refreshTokens, session: refreshSessions })
        .from(refreshTokens)
        .innerJoin(refreshSessions, eq(refreshTokens.sessionId, refreshSessions.id))
        .where(eq(refreshTokens.tokenHash, hash))
        .limit(1)
    )[0];
  }
  async findAccess(hash: string) {
    return (
      await this.db
        .select({ token: accessTokens, session: refreshSessions, user: users })
        .from(accessTokens)
        .innerJoin(refreshSessions, eq(accessTokens.sessionId, refreshSessions.id))
        .innerJoin(users, eq(refreshSessions.userId, users.id))
        .where(eq(accessTokens.tokenHash, hash))
        .limit(1)
    )[0];
  }
  async lockSession(id: string) {
    await this.db.select().from(refreshSessions).where(eq(refreshSessions.id, id)).for('update');
  }
  async consumeRefresh(id: string, at: Date) {
    await this.db.update(refreshTokens).set({ consumedAt: at }).where(eq(refreshTokens.id, id));
  }
  async revokeSession(id: string, at: Date) {
    await this.db.update(refreshSessions).set({ revokedAt: at }).where(eq(refreshSessions.id, id));
  }
  async cleanup(now: Date) {
    await this.db.delete(accessTokens).where(lte(accessTokens.expiresAt, now));
    await this.db.delete(refreshSessions).where(lte(refreshSessions.expiresAt, now));
  }
}
export function createAuthUnitOfWork(db: Database): AuthUnitOfWork {
  return { run: (work) => db.transaction((tx) => work(new AuthRepository(tx))) };
}
