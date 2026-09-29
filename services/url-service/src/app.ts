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

export interface AppDependencies {
  database?: DatabaseClient;
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
                ? {
                    target: 'pino-pretty',
                    options: { colorize: true },
                  }
                : undefined,
          },
  });

  const database = dependencies.database ?? createDatabaseClient(env.DATABASE_URL);
  const repository = new UrlRepository(database.db);
  const service = new UrlService(repository);
  const controller = new UrlController(service, env.PUBLIC_BASE_URL);

  app.addHook('onClose', async () => database.close());
  app.setErrorHandler((error, _request, reply) => {
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
    openapi: { info: { title: 'Lynk URL Service API', version: '1.0.0' } },
  });
  app.register(swaggerUi, { routePrefix: '/documentation' });

  // Register routes
  app.register(healthRoutes, { database });
  app.register(urlRoutes, controller);

  return app;
}
