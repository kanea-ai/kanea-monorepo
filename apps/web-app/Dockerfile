# syntax=docker/dockerfile:1.7
# Multi-stage build for the @kanea/web-app Next.js service.
# Built from the monorepo root: `docker build -f apps/web-app/Dockerfile .`
ARG APP_NAME=web-app
ARG APP_PORT=3000

# ---------- Builder ----------
# Single builder stage: copy workspace metadata + lockfile first so the
# install layer caches on lockfile changes only; then copy the rest of the
# repo and run the Nx build. Order matters — installing AFTER `COPY . .`
# avoids any local node_modules overwriting the workspace install.
FROM node:20-alpine AS builder
ARG APP_NAME
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

# Do NOT set NODE_ENV=production here — pnpm honors it and would skip
# devDependencies (tailwindcss, postcss, typescript), which `next build`
# needs to compile assets. NODE_ENV is set on the runner stage only.
ENV NEXT_TELEMETRY_DISABLED=1

# Workspace skeleton — just enough for `pnpm install` to resolve the graph.
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY nx.json tsconfig.base.json ./
COPY apps/web-app/package.json apps/web-app/package.json
COPY apps/www/package.json apps/www/package.json
COPY apps/admin-panel/package.json apps/admin-panel/package.json
COPY libs ./libs

RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# Now bring in the rest of the source and build.
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

# Next.js standalone output bundles a minimal node_modules + server.js.
# Layout in monorepos: .next/standalone/apps/<name>/server.js
COPY --from=builder --chown=nextjs:nodejs /repo/apps/${APP_NAME}/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/${APP_NAME}/.next/static ./apps/${APP_NAME}/.next/static

USER nextjs
EXPOSE ${APP_PORT}

ENV APP_NAME=${APP_NAME}
CMD ["sh", "-c", "exec node apps/${APP_NAME}/server.js"]
