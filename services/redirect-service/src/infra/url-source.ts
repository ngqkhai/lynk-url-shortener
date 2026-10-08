import { DependencyUnavailableError } from '../errors/app-error.js';
import { RedirectRecord, parseRedirectRecord } from '../schemas/redirect.schema.js';

export interface UrlSource {
  findByShortCode(shortCode: string): Promise<RedirectRecord | undefined>;
}

export class HttpUrlSource implements UrlSource {
  constructor(
    private readonly baseUrl: string,
    private readonly timeoutMs: number,
  ) {}

  async findByShortCode(shortCode: string): Promise<RedirectRecord | undefined> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    timeout.unref();
    try {
      const response = await fetch(
        new URL(`/internal/urls/${encodeURIComponent(shortCode)}`, this.baseUrl),
        { signal: controller.signal },
      );
      if (response.status === 404) return undefined;
      if (!response.ok) throw new DependencyUnavailableError();
      return parseRedirectRecord(await response.json());
    } catch (error) {
      if (error instanceof DependencyUnavailableError) throw error;
      throw new DependencyUnavailableError();
    } finally {
      clearTimeout(timeout);
    }
  }
}
