import { createKafkaEvents, type EventConsumer } from './infra/kafka.js';
import { UrlCreatedHandler, type DeadLetterSink } from './services/url-created.service.js';
import swagger from '@fastify/swagger';
import swaggerUi from '@fastify/swagger-ui';
import fastify, { FastifyInstance } from 'fastify';
import { Env } from './config/env.js';
import { RedirectController } from './controllers/redirect.controller.js';
import { AppError } from './errors/app-error.js';
import { createDatabaseClient, DatabaseClient } from './infra/db.js';
import { RedirectCache, RedisRedirectCache } from './infra/redis.js';
import { HttpUrlSource, UrlSource } from './infra/url-source.js';
import { RedirectRepository, RedirectStore } from './repositories/redirect.repository.js';
import { healthRoutes } from './routes/health.routes.js';
import { redirectRoutes } from './routes/redirect.routes.js';
import { RedirectService } from './services/redirect.service.js';

export interface AppDependencies {
  database?: DatabaseClient;
  repository?: RedirectStore;
  cache?: RedirectCache;
  source?: UrlSource;
  events?: { consumer: EventConsumer; deadLetters: DeadLetterSink };
}

export function buildApp(env: Env, dependencies: AppDependencies = {}): FastifyInstance {
  const app = fastify({
    logger:
      env.NODE_ENV === 'test'
        ? false
        : {
            level: env.LOG_LEVEL,
            transport:
              env.NODE_ENV === 'development'
                ? { target: 'pino-pretty', options: { colorize: true } }
                : undefined,
          },
  });

  const database =
    dependencies.database ??
    createDatabaseClient(env.DATABASE_URL, {
      readinessCacheSeconds: env.DB_READINESS_CACHE_SECONDS,
      connectTimeoutSeconds: env.DB_CONNECT_TIMEOUT_SECONDS,
    });
  const repository = dependencies.repository ?? new RedirectRepository(database.db);
  const cache =
    dependencies.cache ??
    new RedisRedirectCache({
      enabled: env.CACHE_ENABLED,
      url: env.REDIS_URL,
      password: env.REDIS_PASSWORD,
      operationTimeoutMs: env.CACHE_OPERATION_TIMEOUT_MS,
      logger: app.log,
    });
  const source =
    dependencies.source ?? new HttpUrlSource(env.URL_SERVICE_BASE_URL, env.UPSTREAM_TIMEOUT_MS);
  const service = new RedirectService(repository, cache, source, env.CACHE_TTL_SECONDS, app.log);
  const controller = new RedirectController(service);

  const events = env.URL_EVENTS_ENABLED
    ? (dependencies.events ?? createKafkaEvents(env.KAFKA_BROKERS!.split(','), app.log))
    : undefined;
  app.addHook('onReady', async () =>
    events?.consumer.start(
      new UrlCreatedHandler(repository, cache, events.deadLetters, env.CACHE_TTL_SECONDS, app.log),
    ),
  );
  cache.start();
  app.addHook('onClose', async () => {
    await events?.consumer.close();
    await cache.close();
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
    openapi: { info: { title: 'Lynk Redirect Service API', version: '1.0.0' } },
  });
  app.register(swaggerUi, { routePrefix: '/documentation' });
  app.register(healthRoutes, { database, cache });
  app.register(redirectRoutes, controller);

  return app;
}
