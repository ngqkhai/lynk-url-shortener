import { buildApp } from './app.js';
import { loadEnv } from './config/env.js';

const env = loadEnv();
const app = buildApp(env);

async function start(): Promise<void> {
  try {
    const address = await app.listen({ port: env.PORT, host: env.HOST });
    app.log.info({ address }, 'redirect-service listening');
  } catch (error) {
    app.log.error(error);
    process.exit(1);
  }
}

const signals: NodeJS.Signals[] = ['SIGTERM', 'SIGINT'];
for (const signal of signals) {
  process.on(signal, async () => {
    app.log.info({ signal }, 'Shutting down gracefully');
    await app.close();
    process.exit(0);
  });
}

start();
