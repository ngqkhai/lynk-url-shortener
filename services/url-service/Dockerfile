FROM node:24-alpine AS builder
WORKDIR /app
COPY package*.json tsconfig*.json ./
COPY packages/shared/package.json ./packages/shared/
COPY services/url-service/package.json ./services/url-service/
RUN npm ci --workspace=@lynk/shared --workspace=@lynk/url-service
COPY packages/shared/ ./packages/shared/
COPY services/url-service/ ./services/url-service/
RUN npm run build --workspace=@lynk/shared && npm run build --workspace=@lynk/url-service

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3001 HOST=0.0.0.0
COPY package*.json ./
COPY packages/shared/package.json ./packages/shared/
COPY services/url-service/package.json ./services/url-service/
RUN npm ci --workspace=@lynk/shared --workspace=@lynk/url-service --omit=dev && npm cache clean --force
COPY --from=builder /app/packages/shared/dist ./packages/shared/dist
COPY --from=builder /app/services/url-service/dist ./dist
COPY --from=builder /app/services/url-service/drizzle ./drizzle
USER node
EXPOSE 3001
CMD ["node", "dist/server.js"]
