import { customAlphabet } from 'nanoid';
import { randomUUID } from 'node:crypto';
import { urlCreatedSchema } from '@lynk/shared/events';
import { ConflictError, NotFoundError } from '../errors/app-error.js';
import { Url } from '../models/url.model.js';
import type { UrlStore } from '../repositories/url.repository.js';
import type { UrlUnitOfWork } from '../infra/unit-of-work.js';
import { CreateUrlInput } from '../schemas/url.schema.js';

const generateNanoId = customAlphabet(
  '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
  7,
);
const MAX_GENERATION_ATTEMPTS = 5;

export interface UrlServiceOptions {
  generateCode?: () => string;
  unit?: UrlUnitOfWork;
  onCreated?: () => void;
}

export class UrlService {
  private readonly generateCode: () => string;

  constructor(
    private readonly repository: UrlStore,
    private readonly options: UrlServiceOptions = {},
  ) {
    this.generateCode = options.generateCode ?? generateNanoId;
  }

  async create(input: CreateUrlInput, ownerId: string | null = null): Promise<Url> {
    if (input.customAlias) {
      return this.createWithCode(input, input.customAlias, ownerId);
    }

    for (let attempt = 0; attempt < MAX_GENERATION_ATTEMPTS; attempt += 1) {
      try {
        return await this.createWithCode(input, this.generateCode(), ownerId);
      } catch (error) {
        if (!isUniqueViolation(error)) throw error;
      }
    }
    throw new Error('Unable to generate a unique short code');
  }

  async getMetadata(shortCode: string): Promise<Url> {
    const url = await this.repository.findByShortCode(shortCode);
    if (!url) throw new NotFoundError();
    return url;
  }

  async getOwnedMetadata(shortCode: string, ownerId: string): Promise<Url> {
    const url = await this.getMetadata(shortCode);
    if (url.ownerId !== ownerId) throw new NotFoundError();
    return url;
  }

  private async createWithCode(
    input: CreateUrlInput,
    shortCode: string,
    ownerId: string | null,
  ): Promise<Url> {
    try {
      const data = {
        shortCode,
        originalUrl: input.originalUrl,
        expiresAt: input.expiresAt,
        ownerId,
      };
      if (!this.options.unit) return await this.repository.create(data);
      const result = await this.options.unit.run(async (urls, outbox) => {
        const created = await urls.create(data);
        const event = urlCreatedSchema.parse({
          eventId: randomUUID(),
          eventType: 'url.created',
          schemaVersion: 1,
          occurredAt: created.createdAt.toISOString(),
          data: {
            urlId: created.id,
            shortCode: created.shortCode,
            originalUrl: created.originalUrl,
            createdAt: created.createdAt.toISOString(),
            expiresAt: created.expiresAt?.toISOString() ?? null,
            ownerId: created.ownerId,
          },
        });
        await outbox.insert(event);
        return created;
      });
      this.options.onCreated?.();
      return result;
    } catch (error) {
      if (input.customAlias && isUniqueViolation(error)) throw new ConflictError();
      throw error;
    }
  }
}

function isUniqueViolation(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false;
  if (
    'code' in error &&
    error.code === '23505' &&
    'constraint_name' in error &&
    error.constraint_name === 'urls_short_code_unique'
  )
    return true;
  return 'cause' in error && isUniqueViolation(error.cause);
}
