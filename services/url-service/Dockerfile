# Stage 1: Build & Compile TypeScript
FROM node:24-alpine AS builder
WORKDIR /app

# Copy root manifests and workspace configs
COPY package*.json ./
COPY tsconfig*.json ./
COPY services/url-service/package*.json ./services/url-service/
COPY services/url-service/tsconfig*.json ./services/url-service/

RUN npm ci --workspace=@lynk/url-service

COPY services/url-service/src/ ./services/url-service/src/
RUN npm run build --workspace=@lynk/url-service

# Stage 2: Production Minimal Runtime
FROM node:24-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3001
ENV HOST=0.0.0.0

COPY package*.json ./
COPY services/url-service/package*.json ./services/url-service/

RUN npm ci --workspace=@lynk/url-service --omit=dev && npm cache clean --force

COPY --from=builder /app/services/url-service/dist ./dist

# Security: Run as unprivileged non-root user (node uid:1000)
USER node

EXPOSE 3001

CMD ["node", "dist/server.js"]
