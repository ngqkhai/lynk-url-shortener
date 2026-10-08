import { buildApp, buildGatewayApp } from './app.js';
import { loadEnv } from './config/env.js';
const env = loadEnv();
const app = await buildApp(env);
const gateway = env.PHANTOM_ENABLED ? buildGatewayApp(env, app.authService) : undefined;
let closing = false;
async function close() {
  if (closing) return;
  closing = true;
  await gateway?.close();
  await app.close();
}
for (const signal of ['SIGTERM', 'SIGINT'] as const)
  process.on(signal, () => {
    void close().catch((err) => {
      app.log.error({ err }, 'Shutdown failed');
      process.exitCode = 1;
    });
  });
try {
  await gateway?.listen({ port: env.GATEWAY_PORT, host: env.HOST });
  await app.listen({ port: env.PORT, host: env.HOST });
} catch (err) {
  app.log.error({ err }, 'Startup failed');
  await close();
  process.exitCode = 1;
}
