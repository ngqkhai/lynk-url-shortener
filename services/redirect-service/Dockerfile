FROM node:24-alpine AS builder
WORKDIR /app
COPY package*.json tsconfig*.json ./
COPY packages/shared/package.json ./packages/shared/
COPY services/redirect-service/package.json ./services/redirect-service/
RUN npm ci --workspace=@lynk/shared --workspace=@lynk/redirect-service
COPY packages/shared/ ./packages/shared/
COPY services/redirect-service/ ./services/redirect-service/
RUN npm run build --workspace=@lynk/shared && npm run build --workspace=@lynk/redirect-service

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3002 HOST=0.0.0.0
COPY package*.json ./
COPY packages/shared/package.json ./packages/shared/
COPY services/redirect-service/package.json ./services/redirect-service/
RUN npm ci --workspace=@lynk/shared --workspace=@lynk/redirect-service --omit=dev && npm cache clean --force
COPY --from=builder /app/packages/shared/dist ./packages/shared/dist
COPY --from=builder /app/services/redirect-service/dist ./dist
COPY --from=builder /app/services/redirect-service/drizzle ./drizzle
USER node
EXPOSE 3002
CMD ["node", "dist/server.js"]
