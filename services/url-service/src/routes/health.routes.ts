import { FastifyInstance } from 'fastify';

export async function healthRoutes(fastify: FastifyInstance): Promise<void> {
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
    // Sprint 0: Walking skeleton has no DB dependencies yet
    return reply.status(200).send({
      status: 'ready',
      service: 'url-service',
      checks: {
        database: 'not_configured_sprint_0',
      },
    });
  });
}
