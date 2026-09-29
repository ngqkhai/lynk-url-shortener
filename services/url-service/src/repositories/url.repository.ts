import { eq } from 'drizzle-orm';
import { Database } from '../infra/db.js';
import { NewUrl, Url, urls } from '../models/url.model.js';

export class UrlRepository {
  constructor(private readonly db: Database) {}

  async create(url: NewUrl): Promise<Url> {
    const [created] = await this.db.insert(urls).values(url).returning();
    return created;
  }

  async findByShortCode(shortCode: string): Promise<Url | undefined> {
    const [url] = await this.db.select().from(urls).where(eq(urls.shortCode, shortCode)).limit(1);
    return url;
  }
}
