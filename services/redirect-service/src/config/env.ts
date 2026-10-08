import { z } from 'zod';

const booleanString = z
  .enum(['true', 'false'])
  .default('true')
  .transform((value) => value === 'true');

export const envSchema = z
  .object({
    NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
    PORT: z.coerce.number().int().positive().default(3002),
    HOST: z.string().default('0.0.0.0'),
    LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
    DATABASE_URL: z.string().url(),
    DB_READINESS_CACHE_SECONDS: z.coerce.number().int().min(0).default(0),
    DB_CONNECT_TIMEOUT_SECONDS: z.coerce.number().int().positive().default(2),
    REDIS_URL: z.string().url(),
    REDIS_PASSWORD: z.string().optional(),
    URL_SERVICE_BASE_URL: z.string().url(),
    CACHE_ENABLED: booleanString,
    CACHE_TTL_SECONDS: z.coerce.number().int().positive().default(3600),
    CACHE_OPERATION_TIMEOUT_MS: z.coerce.number().int().positive().default(50),
    URL_EVENTS_ENABLED: z
      .enum(['true', 'false'])
      .default('false')
      .transform((value) => value === 'true'),
    KAFKA_BROKERS: z.string().min(1).optional(),
    UPSTREAM_TIMEOUT_MS: z.coerce.number().int().positive().default(500),
  })
  .superRefine((env, ctx) => {
    if (env.URL_EVENTS_ENABLED && !env.KAFKA_BROKERS)
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['KAFKA_BROKERS'],
        message: 'Required when events enabled',
      });
  });

export type Env = z.infer<typeof envSchema>;

export function loadEnv(): Env {
  const result = envSchema.safeParse(process.env);
  if (!result.success) {
    console.error('Invalid environment configuration:', result.error.format());
    process.exit(1);
  }
  return result.data;
}
