# syntax=docker/dockerfile:1.7
# Multi-stage build for the @kanea/www Next.js service.
# Built from the monorepo root: `docker build -f apps/www/Dockerfile .`
ARG APP_NAME=www
ARG APP_PORT=3001

# ---------- Deps ----------
FROM node:20-alpine AS deps
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY nx.json tsconfig.base.json ./
COPY apps/web-app/package.json apps/web-app/package.json
COPY apps/www/package.json apps/www/package.json
COPY apps/admin-panel/package.json apps/admin-panel/package.json
COPY libs ./libs

RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# ---------- Builder ----------
FROM node:20-alpine AS builder
ARG APP_NAME
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /repo/node_modules ./node_modules
COPY . .

RUN pnpm --filter "@kanea/${APP_NAME}" build

# ---------- Runner ----------
FROM node:20-alpine AS runner
ARG APP_NAME
ARG APP_PORT
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=${APP_PORT} \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /repo/apps/${APP_NAME}/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/${APP_NAME}/.next/static ./apps/${APP_NAME}/.next/static

USER nextjs
EXPOSE ${APP_PORT}

ENV APP_NAME=${APP_NAME}
CMD ["sh", "-c", "exec node apps/${APP_NAME}/server.js"]
