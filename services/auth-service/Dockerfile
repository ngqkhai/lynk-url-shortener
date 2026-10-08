FROM node:24-alpine AS builder
WORKDIR /app
COPY package*.json tsconfig*.json ./
COPY packages/shared/package.json ./packages/shared/
COPY services/auth-service/package.json ./services/auth-service/
RUN npm ci --workspace=@lynk/shared --workspace=@lynk/auth-service
COPY packages/shared/ ./packages/shared/
COPY services/auth-service/ ./services/auth-service/
RUN npm run build --workspace=@lynk/shared && npm run build --workspace=@lynk/auth-service

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3004 HOST=0.0.0.0
COPY package*.json ./
COPY packages/shared/package.json ./packages/shared/
COPY services/auth-service/package.json ./services/auth-service/
RUN npm ci --workspace=@lynk/shared --workspace=@lynk/auth-service --omit=dev && npm cache clean --force
COPY --from=builder /app/packages/shared/dist ./packages/shared/dist
COPY --from=builder /app/services/auth-service/dist ./dist
COPY --from=builder /app/services/auth-service/drizzle ./drizzle
USER node
EXPOSE 3004 3005
CMD ["node", "dist/server.js"]
