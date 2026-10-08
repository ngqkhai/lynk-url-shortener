import { z } from 'zod';
export const envSchema = z
  .object({
    NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
    HOST: z.string().default('0.0.0.0'),
    PORT: z.coerce.number().int().positive().default(3004),
    LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
    DATABASE_URL: z.string().url(),
    DB_READINESS_CACHE_SECONDS: z.coerce.number().int().min(0).default(0),
    DB_CONNECT_TIMEOUT_SECONDS: z.coerce.number().int().positive().default(2),
    JWT_PRIVATE_KEY_PATH: z.string().min(1),
    JWT_PUBLIC_KEY_PATH: z.string().min(1),
    JWT_KEY_ID: z.string().default('lynk-local-1'),
    PHANTOM_ENABLED: z
      .enum(['true', 'false'])
      .default('false')
      .transform((v) => v === 'true'),
    GATEWAY_PORT: z.coerce.number().int().positive().default(3005),
    GATEWAY_CA_PATH: z.string().optional(),
    GATEWAY_CERT_PATH: z.string().optional(),
    GATEWAY_KEY_PATH: z.string().optional(),
    GATEWAY_CLIENT_CN: z.string().default('lynk-traefik'),
  })
  .superRefine((env, ctx) => {
    if (
      env.PHANTOM_ENABLED &&
      (!env.GATEWAY_CA_PATH || !env.GATEWAY_CERT_PATH || !env.GATEWAY_KEY_PATH)
    )
      ctx.addIssue({ code: 'custom', message: 'Phantom listener requires mTLS certificate paths' });
  });
export type Env = z.infer<typeof envSchema>;
export const loadEnv = (): Env => envSchema.parse(process.env);
