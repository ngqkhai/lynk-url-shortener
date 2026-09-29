import { customAlphabet } from 'nanoid';
import { ConflictError, NotFoundError } from '../errors/app-error.js';
import { Url } from '../models/url.model.js';
import { UrlRepository } from '../repositories/url.repository.js';
import { CreateUrlInput } from '../schemas/url.schema.js';

const generateNanoId = customAlphabet(
  '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
  7,
);
const MAX_GENERATION_ATTEMPTS = 5;

export interface UrlServiceOptions {
  generateCode?: () => string;
}

export class UrlService {
  private readonly generateCode: () => string;

  constructor(
    private readonly repository: UrlRepository,
    options: UrlServiceOptions = {},
  ) {
    this.generateCode = options.generateCode ?? generateNanoId;
  }

  async create(input: CreateUrlInput): Promise<Url> {
    if (input.customAlias) {
      return this.createWithCode(input, input.customAlias);
    }

    for (let attempt = 0; attempt < MAX_GENERATION_ATTEMPTS; attempt += 1) {
      try {
        return await this.createWithCode(input, this.generateCode());
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

  private async createWithCode(input: CreateUrlInput, shortCode: string): Promise<Url> {
    try {
      return await this.repository.create({
        shortCode,
        originalUrl: input.originalUrl,
        expiresAt: input.expiresAt,
      });
    } catch (error) {
      if (input.customAlias && isUniqueViolation(error)) throw new ConflictError();
      throw error;
    }
  }
}

function isUniqueViolation(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false;
  if ('code' in error && error.code === '23505') return true;
  return 'cause' in error && isUniqueViolation(error.cause);
}
