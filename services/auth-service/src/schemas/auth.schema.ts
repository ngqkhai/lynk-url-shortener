import { z } from 'zod';
import { opaqueRefreshSchema } from '@lynk/shared/auth';
export const credentialsSchema = z.object({
  email: z.string().trim().toLowerCase().email().max(254),
  password: z.string().min(12).max(128),
});
export const refreshSchema = z.object({ refreshToken: opaqueRefreshSchema });
