FROM node:24-alpine AS builder
WORKDIR /app

COPY package*.json ./
COPY tsconfig*.json ./
COPY services/redirect-service/package*.json ./services/redirect-service/
COPY services/redirect-service/tsconfig*.json ./services/redirect-service/
RUN npm ci --workspace=@lynk/redirect-service

COPY services/redirect-service/src/ ./services/redirect-service/src/
COPY services/redirect-service/drizzle/ ./services/redirect-service/drizzle/
RUN npm run build --workspace=@lynk/redirect-service

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3002
ENV HOST=0.0.0.0

COPY package*.json ./
COPY services/redirect-service/package*.json ./services/redirect-service/
RUN npm ci --workspace=@lynk/redirect-service --omit=dev && npm cache clean --force

COPY --from=builder /app/services/redirect-service/dist ./dist
COPY --from=builder /app/services/redirect-service/drizzle ./drizzle

USER node
EXPOSE 3002
CMD ["node", "dist/server.js"]
