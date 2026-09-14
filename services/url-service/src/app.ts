import fastify, { FastifyInstance } from 'fastify';
import { healthRoutes } from './routes/health.routes.js';
import { Env } from './config/env.js';

export function buildApp(env: Env): FastifyInstance {
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

  // Register routes
  app.register(healthRoutes);

  return app;
}
