import { z } from 'zod';

export const shortCodeParamsSchema = z.object({ shortCode: z.string().min(1).max(32) });

export const redirectRecordSchema = z.object({
  shortCode: z.string(),
  originalUrl: z.string().url(),
  expiresAt: z.string().datetime({ offset: true }).nullable(),
  ownerId: z.string().uuid().nullable().default(null),
});

export interface RedirectRecord {
  shortCode: string;
  originalUrl: string;
  expiresAt: Date | null;
  ownerId?: string | null;
}

export function parseRedirectRecord(input: unknown): RedirectRecord {
  const parsed = redirectRecordSchema.parse(input);
  return {
    ...parsed,
    expiresAt: parsed.expiresAt ? new Date(parsed.expiresAt) : null,
  };
}
