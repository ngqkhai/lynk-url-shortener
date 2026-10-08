import { z } from 'zod';

const aliasPattern = /^[A-Za-z0-9]{3,32}$/;
export const reservedAliases = new Set(['api', 'health']);

export const createUrlSchema = z.object({
  originalUrl: z
    .string()
    .url()
    .refine((value) => {
      const protocol = new URL(value).protocol;
      return protocol === 'http:' || protocol === 'https:';
    }, 'originalUrl must use http or https'),
  customAlias: z
    .string()
    .regex(aliasPattern, 'customAlias must be Base62 and 3-32 characters')
    .optional()
    .refine(
      (value) => value === undefined || !reservedAliases.has(value),
      'customAlias is reserved',
    ),
  expiresAt: z
    .string()
    .datetime({ offset: true })
    .optional()
    .transform((value) => (value ? new Date(value) : undefined))
    .refine(
      (value) => value === undefined || value > new Date(),
      'expiresAt must be in the future',
    ),
});

export const shortCodeParamsSchema = z.object({
  shortCode: z.string().min(1).max(32),
});

export type CreateUrlInput = z.infer<typeof createUrlSchema>;
