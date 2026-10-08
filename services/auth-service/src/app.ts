import fastify, { type FastifyInstance } from 'fastify';
import rateLimit from '@fastify/rate-limit';
import swagger from '@fastify/swagger';
import swaggerUi from '@fastify/swagger-ui';
import { readFileSync } from 'node:fs';
import { TLSSocket } from 'node:tls';
import { importPKCS8 } from 'jose';
import {
  createPrincipalVerifier,
  signInternalToken,
  type PrincipalVerifier,
} from '@lynk/shared/auth';
import type { Env } from './config/env.js';
import { createDatabaseClient, type DatabaseClient } from './infra/db.js';
import { createPasswordHasher, type PasswordHasher } from './infra/password.js';
import {
  AuthRepository,
  createAuthUnitOfWork,
  type AuthStore,
  type AuthUnitOfWork,
} from './repositories/auth.repository.js';
import { AuthService, type InternalSigner } from './services/auth.service.js';
import { AuthController } from './controllers/auth.controller.js';
import { authRoutes } from './routes/auth.routes.js';
import { healthRoutes } from './routes/health.routes.js';
import { AppError } from './errors/app-error.js';

export interface AppDependencies {
  database?: DatabaseClient;
  store?: AuthStore;
  unit?: AuthUnitOfWork;
  passwords?: PasswordHasher;
  signer?: InternalSigner;
  verify?: PrincipalVerifier;
  now?: () => Date;
}
export type AuthApp = FastifyInstance & { authService: AuthService };
function installErrorHandler(app: FastifyInstance) {
  app.setErrorHandler((error, _request, reply) => {
    if (error instanceof AppError)
      return reply
        .code(error.statusCode)
        .send({ error: { code: error.code, message: error.message } });
    if (error instanceof Error && ('issues' in error || 'validation' in error))
      return reply
        .code(400)
        .send({ error: { code: 'VALIDATION_ERROR', message: 'Invalid request' } });
    if (
      typeof error === 'object' &&
      error !== null &&
      'statusCode' in error &&
      error.statusCode === 429
    )
      return reply
        .code(429)
        .send({ error: { code: 'RATE_LIMITED', message: 'Too many requests' } });
    app.log.error({ err: error }, 'Auth request failed');
    return reply
      .code(500)
      .send({ error: { code: 'INTERNAL_ERROR', message: 'Internal server error' } });
  });
}
export async function buildApp(env: Env, deps: AppDependencies = {}): Promise<AuthApp> {
  const app = fastify({
    logger:
      env.NODE_ENV === 'test'
        ? false
        : {
            level: env.LOG_LEVEL,
            redact: ['req.headers.authorization', 'password', 'accessToken', 'refreshToken'],
          },
  });
  const database =
    deps.database ??
    createDatabaseClient(env.DATABASE_URL, {
      readinessCacheSeconds: env.DB_READINESS_CACHE_SECONDS,
      connectTimeoutSeconds: env.DB_CONNECT_TIMEOUT_SECONDS,
    });
  const store = deps.store ?? new AuthRepository(database.db);
  const unit = deps.unit ?? createAuthUnitOfWork(database.db);
  const key = deps.signer
    ? undefined
    : await importPKCS8(readFileSync(env.JWT_PRIVATE_KEY_PATH, 'utf8'), 'RS256');
  const signer =
    deps.signer ??
    ({
      sign: (principal, expiry, now) =>
        signInternalToken(key!, env.JWT_KEY_ID, principal, expiry, now),
    } satisfies InternalSigner);
  const verify =
    deps.verify ?? createPrincipalVerifier(readFileSync(env.JWT_PUBLIC_KEY_PATH, 'utf8'));
  const service = new AuthService(
    store,
    unit,
    deps.passwords ?? createPasswordHasher(),
    signer,
    deps.now,
  );
  app.decorate('authService', service);
  const controller = new AuthController(service, verify);
  installErrorHandler(app);
  app.register(rateLimit, { global: false });
  app.register(swagger, {
    openapi: {
      info: { title: 'Lynk Auth Service', version: '0.3.0' },
      components: {
        securitySchemes: {
          bearerAuth: {
            type: 'http',
            scheme: 'bearer',
            description: 'Opaque access token through Traefik',
          },
        },
      },
    },
  });
  app.register(swaggerUi, { routePrefix: '/documentation' });
  app.register(authRoutes, controller);
  app.register(healthRoutes, { database });
  let cleanup: ReturnType<typeof setInterval> | undefined;
  app.addHook('onReady', async () => {
    if (env.NODE_ENV !== 'test') {
      cleanup = setInterval(() => {
        void store.cleanup(new Date()).catch((err) => app.log.warn({ err }, 'Auth cleanup failed'));
      }, 86400000);
      cleanup.unref();
    }
  });
  app.addHook('onClose', async () => {
    clearInterval(cleanup);
    await database.close();
  });
  return app as unknown as AuthApp;
}
export function buildGatewayApp(env: Env, service: AuthService): FastifyInstance {
  if (!env.PHANTOM_ENABLED) throw new Error('Phantom listener is disabled');
  const app = fastify({
    logger:
      env.NODE_ENV === 'test'
        ? false
        : {
            level: env.LOG_LEVEL,
            redact: ['req.headers.authorization', 'res.headers.authorization'],
          },
    https: {
      ca: readFileSync(env.GATEWAY_CA_PATH!),
      cert: readFileSync(env.GATEWAY_CERT_PATH!),
      key: readFileSync(env.GATEWAY_KEY_PATH!),
      requestCert: true,
      rejectUnauthorized: true,
    },
  });
  installErrorHandler(app);
  app.addHook('onRequest', async (request, reply) => {
    const socket = request.raw.socket;
    if (
      !(socket instanceof TLSSocket) ||
      !socket.authorized ||
      socket.getPeerCertificate().subject?.CN !== env.GATEWAY_CLIENT_CN
    )
      return reply
        .code(403)
        .send({ error: { code: 'GATEWAY_FORBIDDEN', message: 'Gateway authentication required' } });
  });
  const controller = new AuthController(service, async () => {
    throw new Error('Not supported');
  });
  app.get('/internal/auth/forward', controller.forward.bind(controller));
  return app;
}
