import { z } from 'zod';

export const urlCreatedSchema = z.object({
  eventId: z.string().uuid(),
  eventType: z.literal('url.created'),
  schemaVersion: z.literal(1),
  occurredAt: z.string().datetime({ offset: true }),
  data: z.object({
    urlId: z.string().uuid(),
    shortCode: z.string().regex(/^[A-Za-z0-9]{1,32}$/),
    originalUrl: z
      .string()
      .url()
      .refine((url) => ['http:', 'https:'].includes(new URL(url).protocol)),
    createdAt: z.string().datetime({ offset: true }),
    expiresAt: z.string().datetime({ offset: true }).nullable(),
    ownerId: z.string().uuid().nullable(),
  }),
});
export type UrlCreated = z.infer<typeof urlCreatedSchema>;
