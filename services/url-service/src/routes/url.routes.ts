import { FastifyInstance } from 'fastify';
import { UrlController } from '../controllers/url.controller.js';

const urlResponseSchema = {
  type: 'object',
  required: ['id', 'shortCode', 'shortUrl', 'originalUrl', 'createdAt', 'expiresAt'],
  properties: {
    id: { type: 'string', format: 'uuid' },
    shortCode: { type: 'string' },
    shortUrl: { type: 'string', format: 'uri' },
    originalUrl: { type: 'string', format: 'uri' },
    createdAt: { type: 'string', format: 'date-time' },
    expiresAt: { type: ['string', 'null'], format: 'date-time' },
  },
};

export async function urlRoutes(app: FastifyInstance, controller: UrlController): Promise<void> {
  app.post(
    '/api/v1/urls',
    {
      schema: {
        tags: ['URLs'],
        body: {
          type: 'object',
          required: ['originalUrl'],
          properties: {
            originalUrl: { type: 'string', format: 'uri' },
            customAlias: { type: 'string', pattern: '^[A-Za-z0-9]{3,32}$' },
            expiresAt: { type: 'string', format: 'date-time' },
          },
        },
        response: { 201: urlResponseSchema },
      },
    },
    controller.create.bind(controller),
  );
  app.get(
    '/api/v1/urls/:shortCode',
    {
      schema: { tags: ['URLs'], response: { 200: urlResponseSchema } },
    },
    controller.getMetadata.bind(controller),
  );
  app.get(
    '/internal/urls/:shortCode',
    {
      schema: {
        tags: ['Internal'],
        response: {
          200: {
            type: 'object',
            required: ['shortCode', 'originalUrl', 'expiresAt'],
            properties: {
              shortCode: { type: 'string' },
              originalUrl: { type: 'string', format: 'uri' },
              expiresAt: { type: ['string', 'null'], format: 'date-time' },
            },
          },
        },
      },
    },
    controller.getInternal.bind(controller),
  );
}
