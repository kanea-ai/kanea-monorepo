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
(cd apps/api && poetry install)
pre-commit install
```

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
