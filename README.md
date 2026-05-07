# kanea-monorepo

Nx-managed monorepo for the Kanea platform. TypeScript apps live alongside a Python FastAPI service; Nx handles task orchestration and caching across both stacks.

## Layout

```
.
├── apps/
│   ├── admin-panel/   # Next.js (App Router + Tailwind), port 3002
│   ├── api/           # FastAPI service, Poetry-managed
│   ├── web-app/       # Next.js (App Router + Tailwind), port 3000
│   └── www/           # Next.js (App Router + Tailwind), port 3001
├── libs/              # shared packages (empty)
├── infra/
│   └── opentofu/      # IaC
├── nx.json            # task graph + caching config
├── pnpm-workspace.yaml
├── pyproject (per-app)
├── tsconfig.base.json # path aliases shared by all TS projects
└── .pre-commit-config.yaml
```

## Prerequisites

- Node `>=20.11`, pnpm `>=9`
- Python `3.12`, Poetry `>=1.8`
- `pre-commit` (`pipx install pre-commit`)

## First-time setup

```bash
pnpm install
(cd apps/api && poetry env use python3.12 && poetry install)
pre-commit install
```

> Poetry must use Python 3.12 (matches the prod Dockerfile). If your default
> `python` is 3.13/3.14, the explicit `poetry env use python3.12` step keeps
> the local venv aligned with prod and avoids missing-wheel surprises.

## Local development (inner loop)

Apps run on the host (so Next.js HMR + uvicorn `--reload` work normally).
Only Postgres lives in Docker — matches Cloud SQL major version 15.

```bash
pnpm dev:db          # start Postgres on :5432
pnpm dev:migrate     # alembic upgrade head against the local DB
pnpm dev             # nx run-many -t dev (api :8000 + 3 Next.js apps)
```

Then open:

| URL                            | App                |
| ------------------------------ | ------------------ |
| `http://localhost:3000`        | `web-app` (SaaS)   |
| `http://localhost:3000/signup` | Create a workspace |
| `http://localhost:3001`        | `www` (marketing)  |
| `http://localhost:3002`        | `admin-panel`      |
| `http://localhost:8000/docs`   | FastAPI Swagger UI |

DB lifecycle:

| Command             | What it does                                       |
| ------------------- | -------------------------------------------------- |
| `pnpm dev:db`       | Start Postgres (data persists in volume)           |
| `pnpm dev:db:logs`  | Tail Postgres logs                                 |
| `pnpm dev:db:stop`  | Stop the container; data persists                  |
| `pnpm dev:db:reset` | Stop **and drop the volume** — fresh DB next start |

### Env files

- `apps/api/.env.development` (committed) — shared dev defaults.
  Personal overrides go in `apps/api/.env` (gitignored). Later wins.
- `apps/{web-app,www,admin-panel}/.env.development` (committed) — shared dev
  defaults. Personal overrides go in `.env.development.local` (gitignored).

The defaults align with `pnpm dev:db` out of the box (`kanea/kanea/kanea`),
so a fresh clone needs zero env-var fiddling.

## Common commands

| Command                      | What it does                           |
| ---------------------------- | -------------------------------------- |
| `pnpm dev`                   | Run every app's dev target in parallel |
| `nx run web-app:dev`         | Run a single app                       |
| `nx run-many -t build`       | Build all projects (cached)            |
| `nx affected -t lint test`   | Lint + test only changed projects      |
| `nx graph`                   | Open the project graph                 |
| `pnpm format`                | Prettier across the workspace          |
| `pre-commit run --all-files` | Run every hook locally                 |

## Caching

`nx.json` defines `namedInputs` (`default`, `production`, `sharedGlobals`) and turns caching on for `build`, `lint`, `test`, and `e2e`. The `production` input excludes test files, snapshots, and per-project lint configs so changing a test does not bust a build cache. Outputs are declared per-target so Nx restores `.next/`, `dist/`, and `build/` artifacts on cache hits.

## Pre-commit

Configured hooks (`.pre-commit-config.yaml`):

- **Yelp `detect-secrets`** — scans staged diffs against `.secrets.baseline`
- **Black** — formats `apps/api/**/*.py`
- **Prettier** — formats JS/TS/JSON/YAML/Markdown/CSS
- Misc: trailing whitespace, EOF, large files, merge conflicts, private keys

To regenerate the secrets baseline after reviewing findings:

```bash
detect-secrets scan --baseline .secrets.baseline
detect-secrets audit .secrets.baseline
```
