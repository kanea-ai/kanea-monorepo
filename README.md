# Kanea.ai Monorepo

[![PR Checks](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/pr-checks.yml/badge.svg?branch=main)](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/pr-checks.yml)
[![Deploy](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/deploy.yml)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey.svg)](#license)

---

## Overview

**Kanea.ai** is an enterprise SaaS platform for AI orchestration — a shared workspace where humans and autonomous agents operate on the same backlog. Teams delegate work down a priority hierarchy, surface blockers as they happen, and keep humans in the loop where it matters. Kanea provides multi-tenant workspaces, departments, teams, and projects on top of a rich Kanban-style task model with first-class support for agent assignees, cross-team requests, and a full audit trail.

The platform is built as an Nx-managed monorepo: three Next.js applications (marketing site, SaaS dashboard, internal admin panel) backed by a single FastAPI service in front of PostgreSQL. Everything ships to Google Cloud Platform — Cloud Run for compute, Cloud SQL for data, Secret Manager for credentials, Cloud Armor for edge protection — all provisioned with OpenTofu and deployed continuously through GitHub Actions.

---

## Repository Structure

```
kanea-monorepo/
├── apps/
│   ├── api/            # FastAPI service (Python 3.12, Poetry, SQLAlchemy 2.x async)
│   ├── web-app/        # SaaS dashboard (Next.js 14, App Router) — port 3000
│   ├── www/            # Marketing landing site (Next.js 14)        — port 3001
│   └── admin-panel/    # Internal back-office console (Next.js 14)  — port 3002
├── infra/
│   └── opentofu/       # GCP infrastructure as code (Cloud Run, Cloud SQL, LB, WIF, …)
├── libs/               # Shared workspace packages
├── .github/workflows/  # CI (pr-checks.yml) and CD (deploy.yml)
├── docker-compose.local.yml  # Local Postgres 15 for development
├── nx.json             # Nx task graph, caching, and namedInputs
├── pnpm-workspace.yaml
└── tsconfig.base.json
```

| Path               | Purpose                                                                                       |
| ------------------ | --------------------------------------------------------------------------------------------- |
| `apps/api`         | Hexagonal FastAPI service. Owns all data access, business logic, RBAC, auth, and migrations.  |
| `apps/web-app`     | The tenant-facing dashboard. Kanban board, projects, blocks, directory, audit, profile.       |
| `apps/www`         | The public marketing site at `kanea.ai` / `www.kanea.ai`.                                     |
| `apps/admin-panel` | Cross-tenant operator console for internal Kanea staff. Not publicly invocable.               |
| `infra/opentofu`   | OpenTofu codebase for both prod and staging environments (single state bucket, env-suffixed). |

---

## Tech Stack Overview

- **Frontend:** Next.js 14 (App Router), React 18, TailwindCSS, TanStack Query
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic, asyncpg, bcrypt, PyJWT
- **Data:** PostgreSQL 15 (Cloud SQL with Private Service Access in prod)
- **Infrastructure:** OpenTofu 1.8, Google Cloud Platform (Cloud Run, Cloud SQL, Secret Manager, Cloud Armor, Artifact Registry, Workload Identity Federation), GitHub Actions
- **Tooling:** Nx 20 (monorepo), pnpm 9 (JS workspace), Poetry (Python deps), Docker (BuildKit), pre-commit (Black, Ruff, Prettier, Detect Secrets)

---

## Local Development (The Inner Loop)

Apps run on the host machine so Next.js HMR and `uvicorn --reload` work normally. Only Postgres lives in Docker — pinned to the same major version as Cloud SQL.

### Prerequisites

- **Node.js** `>= 20.11`
- **pnpm** `>= 9` (enable via `corepack enable && corepack prepare pnpm@9.12.0 --activate`)
- **Python** `3.12` (the repo pins `~3.12` exactly — avoid 3.13+ until greenlet wheels catch up)
- **Poetry** `>= 1.8`
- **Docker** (for the local Postgres container)
- **pre-commit** (`pipx install pre-commit`)

### Environment variables

Each app reads its config from per-app `.env` files. The committed `.env.development` files contain shared dev defaults that work against the Dockerised Postgres out of the box — a fresh clone needs zero env-var editing to boot.

```bash
# (optional) seed personal overrides for the API
cp apps/api/.env.example apps/api/.env
```

| File                                                    | Status     | Purpose                            |
| ------------------------------------------------------- | ---------- | ---------------------------------- |
| `apps/api/.env.development`                             | committed  | Shared API dev defaults            |
| `apps/api/.env`                                         | gitignored | Personal API overrides (wins)      |
| `apps/{web-app,www,admin-panel}/.env.development`       | committed  | Shared frontend dev defaults       |
| `apps/{web-app,www,admin-panel}/.env.development.local` | gitignored | Personal frontend overrides (wins) |

### 1. Install dependencies

```bash
pnpm install
(cd apps/api && poetry env use python3.12 && poetry install)
pre-commit install
```

### 2. Start the database

```bash
pnpm dev:db          # docker compose up -d postgres:15-alpine on :5432
pnpm dev:migrate     # alembic upgrade head against the local DB
```

| Command             | What it does                                            |
| ------------------- | ------------------------------------------------------- |
| `pnpm dev:db`       | Start Postgres (data persists in a named Docker volume) |
| `pnpm dev:db:logs`  | Tail Postgres logs                                      |
| `pnpm dev:db:stop`  | Stop the container; data persists                       |
| `pnpm dev:db:reset` | Stop **and drop the volume** — fresh DB next start      |

### 3. Run the stack

```bash
pnpm dev             # nx run-many -t dev — boots all 4 apps in parallel
```

Or run individual apps:

```bash
nx run api:dev          # FastAPI on :8000 (with --reload)
nx run web-app:dev      # SaaS dashboard on :3000
nx run www:dev          # Marketing site on :3001
nx run admin-panel:dev  # Admin panel on :3002
```

### Service URLs

| URL                            | App                |
| ------------------------------ | ------------------ |
| `http://localhost:3000`        | `web-app` (SaaS)   |
| `http://localhost:3000/signup` | Create a workspace |
| `http://localhost:3001`        | `www` (marketing)  |
| `http://localhost:3002`        | `admin-panel`      |
| `http://localhost:8000`        | FastAPI service    |
| `http://localhost:8000/docs`   | Swagger UI         |

### Common commands

| Command                      | What it does                               |
| ---------------------------- | ------------------------------------------ |
| `pnpm dev`                   | Run every app's dev target in parallel     |
| `pnpm build`                 | Build all projects (Nx-cached)             |
| `pnpm lint`                  | Lint everything                            |
| `pnpm test`                  | Run all test suites                        |
| `nx affected -t lint test`   | Lint + test only what changed since `main` |
| `nx graph`                   | Open the visual project graph              |
| `pnpm format`                | Prettier across the workspace              |
| `pre-commit run --all-files` | Run every hook locally                     |

---

## Deployment & CI/CD (The Outer Loop)

Deployments are fully automated. GitHub Actions authenticates to GCP via **Workload Identity Federation** — there are no service-account JSON keys checked in or stored as repo secrets. Every push to a deploy branch builds the four service images in parallel, applies the OpenTofu plan for the target environment, then rolls a new revision onto Cloud Run.

| Branch | Target environment | Public URLs                                                       |
| ------ | ------------------ | ----------------------------------------------------------------- |
| `main` | **prod**           | `kanea.ai`, `www.kanea.ai`, `app.kanea.ai`                        |
| `dev`  | **staging**        | `staging.kanea.ai` (deny-all Cloud Armor outside allowlisted IPs) |

Pipeline stages — see `.github/workflows/deploy.yml`:

1. **plan** — resolves the target environment, image tag (commit SHA), and OpenTofu state prefix.
2. **build** _(matrix: api / web-app / www / admin-panel)_ — multi-stage Docker builds pushed to Artifact Registry with registry-backed buildx cache.
3. **deploy-infra** — `tofu init` + `tofu apply` against the env's tfvars file.
4. **deploy** _(matrix)_ — `gcloud run services update` rolls the new image onto each Cloud Run service.

Pull requests run a separate workflow (`pr-checks.yml`): pre-commit hooks (Black, Ruff, Prettier, Detect Secrets) followed by the full pytest suite against a Postgres 16 sidecar, gated at **≥ 90% coverage**.

---

## API Documentation & Deep Dives

Once the API is running locally, the interactive OpenAPI documentation is available at:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

All routes are mounted under the `/api/v1` prefix — e.g. `POST /api/v1/auth/login`.

For comprehensive architecture, database, infrastructure, and CI/CD documentation, see the technical deep-dive in **[`docs/architecture.md`](docs/architecture.md)** (or `docu.txt` if you received it as a standalone artifact). It covers:

- Full GCP topology (VPC, Cloud Run, Cloud SQL, LB, Cloud Armor, WIF)
- Complete database schema with every table, enum, FK, and index
- Backend service decomposition and the RBAC matrix (role × priority × team_role)
- Migration history and the on-startup `alembic upgrade head` design
- Frontend application breakdown and shared component inventory
- Engineering journey: the production incidents we hit and how we fixed them

---

## License

Proprietary. © Kanea.ai — all rights reserved.
