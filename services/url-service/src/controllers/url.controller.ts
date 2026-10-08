import { FastifyReply, FastifyRequest } from 'fastify';
import type { PrincipalVerifier } from '@lynk/shared/auth';
import { AppError } from '../errors/app-error.js';
import { Url } from '../models/url.model.js';
import { CreateUrlInput, createUrlSchema, shortCodeParamsSchema } from '../schemas/url.schema.js';
import { UrlService } from '../services/url.service.js';

export class UrlController {
  constructor(
    private readonly service: UrlService,
    private readonly publicBaseUrl: string,
    private readonly verify?: PrincipalVerifier,
  ) {}

  async create(
    request: FastifyRequest<{ Body: CreateUrlInput }>,
    reply: FastifyReply,
  ): Promise<FastifyReply> {
    const input = createUrlSchema.parse(request.body);
    const ownerId = this.verify ? (await this.principal(request)).userId : null;
    const url = await this.service.create(input, ownerId);
    return reply.status(201).send(this.serialize(url));
  }

  async getMetadata(
    request: FastifyRequest<{ Params: { shortCode: string } }>,
    reply: FastifyReply,
  ): Promise<FastifyReply> {
    const { shortCode } = shortCodeParamsSchema.parse(request.params);
    const url = this.verify
      ? await this.service.getOwnedMetadata(shortCode, (await this.principal(request)).userId)
      : await this.service.getMetadata(shortCode);
    return reply.status(200).send(this.serialize(url));
  }

  async getInternal(
    request: FastifyRequest<{ Params: { shortCode: string } }>,
    reply: FastifyReply,
  ): Promise<FastifyReply> {
    const { shortCode } = shortCodeParamsSchema.parse(request.params);
    const url = await this.service.getMetadata(shortCode);
    return reply.status(200).send({
      shortCode: url.shortCode,
      originalUrl: url.originalUrl,
      expiresAt: url.expiresAt?.toISOString() ?? null,
      ownerId: url.ownerId ?? null,
    });
  }

  private async principal(request: FastifyRequest) {
    try {
      return await this.verify!(request.headers.authorization);
    } catch {
      throw new AppError(401, 'UNAUTHORIZED', 'Valid internal bearer token required');
    }
  }

  private serialize(url: Url) {
    return {
      id: url.id,
      shortCode: url.shortCode,
      shortUrl: new URL(url.shortCode, `${this.publicBaseUrl}/`).toString(),
      originalUrl: url.originalUrl,
      createdAt: url.createdAt.toISOString(),
      expiresAt: url.expiresAt?.toISOString() ?? null,
    };
  }
}
