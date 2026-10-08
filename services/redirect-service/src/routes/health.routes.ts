import { FastifyInstance } from 'fastify';
import { DatabaseClient } from '../infra/db.js';
import { RedirectCache } from '../infra/redis.js';

export interface HealthRouteOptions {
  database: DatabaseClient;
  cache: RedirectCache;
}

export async function healthRoutes(
  app: FastifyInstance,
  options: HealthRouteOptions,
): Promise<void> {
  app.get('/', async (_request, reply) =>
    reply.status(200).send({ service: 'lynk-redirect-service', status: 'operational' }),
  );

  app.get('/health', async (_request, reply) =>
    reply.status(200).send({
      status: 'ok',
      service: 'redirect-service',
      uptime: process.uptime(),
      timestamp: new Date().toISOString(),
    }),
  );

  app.get('/health/ready', async (_request, reply) => {
    try {
      await options.database.ping();
      return reply.status(200).send({
        status: 'ready',
        service: 'redirect-service',
        checks: { database: 'ok', redis: options.cache.status() },
      });
    } catch (error) {
      app.log.error(error, 'Redirect database readiness check failed');
      return reply.status(503).send({
        status: 'not_ready',
        service: 'redirect-service',
        checks: { database: 'unavailable', redis: options.cache.status() },
      });
    }
  });
}
