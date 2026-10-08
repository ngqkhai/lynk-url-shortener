import type { FastifyReply, FastifyRequest } from 'fastify';
import type { PrincipalVerifier } from '@lynk/shared/auth';
import { credentialsSchema, refreshSchema } from '../schemas/auth.schema.js';
import { UnauthorizedError } from '../errors/app-error.js';
import type { AuthService } from '../services/auth.service.js';
export class AuthController {
  constructor(
    private readonly service: AuthService,
    private readonly verify: PrincipalVerifier,
  ) {}
  async register(request: FastifyRequest, reply: FastifyReply) {
    const input = credentialsSchema.parse(request.body);
    return reply.code(201).send({ user: await this.service.register(input.email, input.password) });
  }
  async login(request: FastifyRequest, reply: FastifyReply) {
    const input = credentialsSchema.parse(request.body);
    return reply
      .header('cache-control', 'no-store')
      .send(await this.service.login(input.email, input.password));
  }
  async refresh(request: FastifyRequest, reply: FastifyReply) {
    const input = refreshSchema.parse(request.body);
    return reply
      .header('cache-control', 'no-store')
      .send(await this.service.refresh(input.refreshToken));
  }
  async logout(request: FastifyRequest, reply: FastifyReply) {
    const input = refreshSchema.parse(request.body);
    await this.service.logout(input.refreshToken);
    return reply.code(204).send();
  }
  async me(request: FastifyRequest, reply: FastifyReply) {
    const principal = await this.verify(request.headers.authorization).catch(() => {
      throw new UnauthorizedError();
    });
    return reply.send({ user: await this.service.me(principal.userId) });
  }
  async forward(request: FastifyRequest, reply: FastifyReply) {
    const token = await this.service.exchange(request.headers.authorization);
    return reply
      .header('authorization', `Bearer ${token}`)
      .header('cache-control', 'no-store')
      .code(200)
      .send();
  }
}
