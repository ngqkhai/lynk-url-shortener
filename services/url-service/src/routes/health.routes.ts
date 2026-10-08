import { FastifyInstance } from 'fastify';
import { DatabaseClient } from '../infra/db.js';

export async function healthRoutes(
  fastify: FastifyInstance,
  options: { database: DatabaseClient },
): Promise<void> {
  fastify.get('/', async (_request, reply) => {
    return reply.status(200).send({
      service: 'lynk-url-service',
      version: '0.1.0',
      status: 'operational',
    });
  });

  fastify.get('/health', async (_request, reply) => {
    return reply.status(200).send({
      status: 'ok',
      service: 'url-service',
      uptime: process.uptime(),
      timestamp: new Date().toISOString(),
    });
  });

  fastify.get('/health/ready', async (_request, reply) => {
    try {
      await options.database.ping();
      return reply
        .status(200)
        .send({ status: 'ready', service: 'url-service', checks: { database: 'ok' } });
    } catch (error) {
      fastify.log.error(error, 'Database readiness check failed');
      return reply
        .status(503)
        .send({ status: 'not_ready', service: 'url-service', checks: { database: 'unavailable' } });
    }
  });
}
