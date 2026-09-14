import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app.js';
import { Env } from '../src/config/env.js';

describe('Health and Readiness Routes', () => {
  let app: FastifyInstance;

  const testEnv: Env = {
    NODE_ENV: 'test',
    PORT: 3001,
    HOST: '0.0.0.0',
    LOG_LEVEL: 'fatal',
  };

  beforeAll(async () => {
    app = buildApp(testEnv);
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it('GET / should return service information', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/',
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.payload);
    expect(body.service).toBe('lynk-url-service');
    expect(body.status).toBe('operational');
  });

  it('GET /health should return 200 and ok status', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/health',
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.payload);
    expect(body.status).toBe('ok');
    expect(body.service).toBe('url-service');
    expect(typeof body.uptime).toBe('number');
    expect(typeof body.timestamp).toBe('string');
  });

  it('GET /health/ready should return 200 and ready status', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/health/ready',
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.payload);
    expect(body.status).toBe('ready');
    expect(body.service).toBe('url-service');
  });
});
