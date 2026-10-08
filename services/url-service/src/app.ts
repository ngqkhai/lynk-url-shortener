import fastify, { FastifyInstance } from 'fastify';
import swagger from '@fastify/swagger';
import swaggerUi from '@fastify/swagger-ui';
import { healthRoutes } from './routes/health.routes.js';
import { Env } from './config/env.js';
import { createDatabaseClient, DatabaseClient } from './infra/db.js';
import { UrlRepository } from './repositories/url.repository.js';
import { UrlService } from './services/url.service.js';
import { UrlController } from './controllers/url.controller.js';
import { urlRoutes } from './routes/url.routes.js';
import { AppError } from './errors/app-error.js';
import { readFileSync } from 'node:fs';
import { createPrincipalVerifier, type PrincipalVerifier } from '@lynk/shared/auth';
import { createUrlUnitOfWork } from './infra/unit-of-work.js';
import { createEventPublisher, type EventPublisher } from './infra/kafka.js';
import { OutboxRepository } from './repositories/outbox.repository.js';
import { OutboxDispatcher } from './services/outbox-dispatcher.service.js';

export interface AppDependencies {
  database?: DatabaseClient;
  verify?: PrincipalVerifier;
  publisher?: EventPublisher;
}

export function buildApp(env: Env, dependencies: AppDependencies = {}): FastifyInstance {
  const app = fastify({
    logger:
      env.NODE_ENV === 'test'
        ? false
        : {
            level: env.LOG_LEVEL,
            redact: ['req.headers.authorization'],
            transport:
              env.NODE_ENV === 'development'
                ? {
                    target: 'pino-pretty',
                    options: { colorize: true },
                  }
                : undefined,
          },
  });

  const database =
    dependencies.database ??
    createDatabaseClient(env.DATABASE_URL, {
      readinessCacheSeconds: env.DB_READINESS_CACHE_SECONDS,
      connectTimeoutSeconds: env.DB_CONNECT_TIMEOUT_SECONDS,
    });
  const repository = new UrlRepository(database.db);
  const service = new UrlService(repository, {
    unit: env.URL_EVENTS_ENABLED ? createUrlUnitOfWork(database.db) : undefined,
    onCreated: () => worker?.notify(),
  });
  const verify = env.AUTH_REQUIRED
    ? (dependencies.verify ??
      createPrincipalVerifier(readFileSync(env.JWT_PUBLIC_KEY_PATH!, 'utf8')))
    : undefined;
  const controller = new UrlController(service, env.PUBLIC_BASE_URL, verify);
  const worker = env.URL_EVENTS_ENABLED
    ? new OutboxDispatcher(
        new OutboxRepository(database.db),
        dependencies.publisher ?? createEventPublisher(env.KAFKA_BROKERS!.split(',')),
        app.log,
        env.OUTBOX_IDLE_POLL_MS,
      )
    : undefined;

  app.addHook('onReady', async () => worker?.start());
  app.addHook('onClose', async () => {
    await worker?.close();
    await database.close();
  });
  app.setErrorHandler((error, _request, reply) => {
    if (!(error instanceof AppError) || error.statusCode >= 500) database.invalidateReadiness?.();
    if (error instanceof AppError) {
      return reply
        .status(error.statusCode)
        .send({ error: { code: error.code, message: error.message, details: error.details } });
    }
    if (typeof error === 'object' && error !== null && 'issues' in error) {
      return reply.status(400).send({
        error: { code: 'VALIDATION_ERROR', message: 'Invalid request', details: error.issues },
      });
    }
    if (typeof error === 'object' && error !== null && 'validation' in error) {
      return reply.status(400).send({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Invalid request',
          details: error.validation,
        },
      });
    }
    app.log.error(error);
    return reply
      .status(500)
      .send({ error: { code: 'INTERNAL_ERROR', message: 'Internal server error' } });
  });

  app.register(swagger, {
    openapi: {
      info: { title: 'Lynk URL Service API', version: '1.0.0' },
      components: {
        securitySchemes: {
          bearerAuth: {
            type: 'http',
            scheme: 'bearer',
            description: 'Opaque token through Traefik',
          },
        },
      },
    },
  });
  app.register(swaggerUi, { routePrefix: '/documentation' });

  // Register routes
  app.register(healthRoutes, { database });
  app.register(urlRoutes, controller);

  return app;
}
