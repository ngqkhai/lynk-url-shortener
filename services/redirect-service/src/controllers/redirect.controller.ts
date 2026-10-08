import { FastifyReply, FastifyRequest } from 'fastify';
import { shortCodeParamsSchema } from '../schemas/redirect.schema.js';
import { RedirectService } from '../services/redirect.service.js';

export class RedirectController {
  constructor(private readonly service: RedirectService) {}

  async redirect(
    request: FastifyRequest<{ Params: { shortCode: string } }>,
    reply: FastifyReply,
  ): Promise<FastifyReply> {
    const { shortCode } = shortCodeParamsSchema.parse(request.params);
    const record = await this.service.resolve(shortCode);
    return reply.redirect(record.originalUrl, 302);
  }
}
