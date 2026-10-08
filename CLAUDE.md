# 🤖 Claude AI Engineering Guidelines

This repository uses **[AGENTS.md](./AGENTS.md)** as the single source of truth for engineering standards, architecture rules, and coding conventions.

Please read and strictly follow **[AGENTS.md](./AGENTS.md)** for:

1. **Core Philosophy:** _"Build ➔ Deploy ➔ Measure ➔ Explain"_.
2. **Microservice Data Ownership:** Strict bounded contexts between `url-service`, `redirect-service`, and `analytics-service`.
3. **Layer-Based Architecture:** `routes/` ➔ `controllers/` ➔ `services/` ➔ `repositories/` ➔ `models/`.
4. **TypeScript Conventions:** NodeNext ESM with mandatory `.js` import extensions, Fastify `buildApp()` factory pattern, Zod schemas, Pino structured logging.
5. **Database & Infrastructure Rules:** Expand/Contract migrations via K8s Jobs, Docker non-root users, Kafka KRaft mode.
6. **Pre-flight Checklist:** Running `make lint` and `make test` before completing tasks.
