FROM node:18-alpine AS builder

WORKDIR /usr/src/app

COPY package*.json ./
COPY packages/shared/package*.json ./packages/shared/
COPY apps/api/package*.json ./apps/api/

RUN npm install

COPY tsconfig*.json ./
COPY packages/shared ./packages/shared
COPY apps/api ./apps/api

# Compile dependencies
RUN npm run build:shared
WORKDIR /usr/src/app/apps/api
RUN npx prisma generate
RUN npm run build

FROM node:18-alpine

WORKDIR /usr/src/app

COPY package*.json ./
COPY packages/shared/package*.json ./packages/shared/
COPY apps/api/package*.json ./apps/api/

RUN npm install --omit=dev

COPY --from=builder /usr/src/app/packages/shared/dist ./packages/shared/dist
COPY --from=builder /usr/src/app/apps/api/dist ./apps/api/dist
COPY --from=builder /usr/src/app/apps/api/prisma ./apps/api/prisma

# Run as non-root user for security
RUN addgroup -S gospelpay && adduser -S gospelpay -G gospelpay
USER gospelpay

EXPOSE 5000

ENV NODE_ENV=production

# Use prisma migrate deploy for production (requires migration files)
# Fallback to db push only in development
CMD ["sh", "-c", "if [ \"$NODE_ENV\" = 'production' ]; then npx prisma migrate deploy; else npx prisma db push; fi && node dist/server.js"]
