import type { FastifyInstance } from 'fastify';
import type { AuthController } from '../controllers/auth.controller.js';
const credentials = {
  type: 'object',
  required: ['email', 'password'],
  properties: {
    email: {
      type: 'string',
      maxLength: 512,
      description: 'Trimmed, lowercased and validated by Zod; normalized email max 254 characters',
    },
    password: { type: 'string', minLength: 12, maxLength: 128 },
  },
};
const refresh = {
  type: 'object',
  required: ['refreshToken'],
  properties: { refreshToken: { type: 'string', pattern: '^rt_[A-Za-z0-9_-]{43}$' } },
};
const user = {
  type: 'object',
  required: ['user'],
  properties: {
    user: {
      type: 'object',
      required: ['id', 'email', 'createdAt'],
      properties: {
        id: { type: 'string', format: 'uuid' },
        email: { type: 'string' },
        createdAt: { type: 'string', format: 'date-time' },
      },
    },
  },
};
const tokenPair = {
  type: 'object',
  required: ['accessToken', 'refreshToken', 'tokenType', 'expiresIn'],
  properties: {
    accessToken: { type: 'string', pattern: '^at_[A-Za-z0-9_-]{43}$' },
    refreshToken: { type: 'string', pattern: '^rt_[A-Za-z0-9_-]{43}$' },
    tokenType: { type: 'string', enum: ['Bearer'] },
    expiresIn: { type: 'integer' },
  },
};
export async function authRoutes(app: FastifyInstance, controller: AuthController) {
  app.post(
    '/api/v1/auth/register',
    {
      config: { rateLimit: { max: 5, timeWindow: '1 minute' } },
      schema: { tags: ['Auth'], body: credentials, response: { 201: user } },
    },
    controller.register.bind(controller),
  );
  app.post(
    '/api/v1/auth/login',
    {
      config: { rateLimit: { max: 10, timeWindow: '1 minute' } },
      schema: { tags: ['Auth'], body: credentials, response: { 200: tokenPair } },
    },
    controller.login.bind(controller),
  );
  app.post(
    '/api/v1/auth/refresh',
    {
      config: { rateLimit: { max: 60, timeWindow: '1 minute' } },
      schema: { tags: ['Auth'], body: refresh, response: { 200: tokenPair } },
    },
    controller.refresh.bind(controller),
  );
  app.post(
    '/api/v1/auth/logout',
    { schema: { tags: ['Auth'], body: refresh } },
    controller.logout.bind(controller),
  );
  app.get(
    '/api/v1/auth/me',
    { schema: { tags: ['Auth'], security: [{ bearerAuth: [] }], response: { 200: user } } },
    controller.me.bind(controller),
  );
}
