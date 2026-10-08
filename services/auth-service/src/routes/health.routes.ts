import type { FastifyInstance } from 'fastify';
import type { DatabaseClient } from '../infra/db.js';
export async function healthRoutes(app: FastifyInstance, options: { database: DatabaseClient }) {
  app.get('/health', async () => ({ status: 'ok', service: 'auth-service' }));
  app.get('/health/ready', async (_request, reply) => {
    try {
      await options.database.ping();
      return { status: 'ready', checks: { database: 'ok' } };
    } catch {
      return reply.code(503).send({ status: 'not_ready', checks: { database: 'unavailable' } });
    }
  });
}
