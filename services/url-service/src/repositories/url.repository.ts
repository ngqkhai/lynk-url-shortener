import { eq } from 'drizzle-orm';
import { Database } from '../infra/db.js';
import { NewUrl, Url, urls } from '../models/url.model.js';

export interface UrlStore {
  create(url: NewUrl): Promise<Url>;
  findByShortCode(shortCode: string): Promise<Url | undefined>;
}
export class UrlRepository implements UrlStore {
  constructor(private readonly db: Pick<Database, 'insert' | 'select'>) {}

  async create(url: NewUrl): Promise<Url> {
    const [created] = await this.db.insert(urls).values(url).returning();
    return created;
  }

  async findByShortCode(shortCode: string): Promise<Url | undefined> {
    const [url] = await this.db.select().from(urls).where(eq(urls.shortCode, shortCode)).limit(1);
    return url;
  }
}
