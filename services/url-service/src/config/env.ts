import { z } from 'zod';

export const envSchema = z
  .object({
    NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
    PORT: z.coerce.number().default(3001),
    HOST: z.string().default('0.0.0.0'),
    LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
    DATABASE_URL: z.string().url(),
    DB_READINESS_CACHE_SECONDS: z.coerce.number().int().min(0).default(0),
    DB_CONNECT_TIMEOUT_SECONDS: z.coerce.number().int().positive().default(2),
    PUBLIC_BASE_URL: z.string().url(),
    AUTH_REQUIRED: z
      .enum(['true', 'false'])
      .default('true')
      .transform((v) => v === 'true'),
    JWT_PUBLIC_KEY_PATH: z.string().optional(),
    URL_EVENTS_ENABLED: z
      .enum(['true', 'false'])
      .default('false')
      .transform((v) => v === 'true'),
    KAFKA_BROKERS: z.string().optional(),
    OUTBOX_IDLE_POLL_MS: z.coerce.number().int().min(1000).max(3600000).default(1000),
  })
  .superRefine((env, ctx) => {
    if (env.AUTH_REQUIRED && !env.JWT_PUBLIC_KEY_PATH)
      ctx.addIssue({ code: 'custom', message: 'AUTH_REQUIRED needs JWT_PUBLIC_KEY_PATH' });
    if (env.URL_EVENTS_ENABLED && !env.KAFKA_BROKERS)
      ctx.addIssue({ code: 'custom', message: 'URL_EVENTS_ENABLED needs KAFKA_BROKERS' });
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
