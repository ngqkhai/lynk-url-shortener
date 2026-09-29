import { FastifyInstance } from 'fastify';
import { RedirectController } from '../controllers/redirect.controller.js';

export async function redirectRoutes(
  app: FastifyInstance,
  controller: RedirectController,
): Promise<void> {
  app.get(
    '/:shortCode',
    {
      schema: {
        tags: ['Redirect'],
        params: {
          type: 'object',
          required: ['shortCode'],
          properties: { shortCode: { type: 'string', minLength: 1, maxLength: 32 } },
        },
        response: { 302: { type: 'null' } },
      },
    },
    controller.redirect.bind(controller),
  );
}
