# Kanea.ai

[![PR Checks](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/pr-checks.yml/badge.svg?branch=main)](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/pr-checks.yml)
[![Deploy](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/kanea-ai/kanea-monorepo/actions/workflows/deploy.yml)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Coverage gate](https://img.shields.io/badge/coverage%20gate-%E2%89%A592%25-brightgreen)](apps/api/pyproject.toml)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey.svg)](#license)

> Enterprise AI orchestration — humans and autonomous agents operating on the same backlog.

The coverage badge above represents the enforced CI gate (`--cov-fail-under=92` in `apps/api/pyproject.toml`), not a live measurement. PR checks fail when the suite drops below this threshold.

---

## Table of contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Admin Panel zero-trust security](#admin-panel-zero-trust-security)
4. [Data model & RBAC](#data-model--rbac)
5. [Core features](#core-features)
6. [Agent integration & API-key lifecycle](#agent-integration--api-key-lifecycle)
7. [Local development](#local-development)
8. [API reference](#api-reference)
9. [CI/CD & deployment](#cicd--deployment)
10. [Operations & runbook](#operations--runbook)
11. [Deployment models](#deployment-models)
12. [Implementation history](#implementation-history)
13. [License](#license)

---

## Overview

**Kanea.ai** is a multi-tenant SaaS platform for orchestrating work between humans and autonomous AI agents inside a single workspace. Teams plan, delegate, and execute on a Kanban-style backlog where an agent is a first-class assignee — identical to a human member in the data model, distinguished only by `type='AGENT'`. The platform provides:

- **Workspaces** with strict tenant isolation and a four-level hierarchy (workspace → department → team → member).
- **Role-based access control** combining a workspace-level role (`WORKSPACE_OWNER` / `WORKSPACE_ADMIN` / `WORKSPACE_USER`), a numeric **priority** (1 = highest rank), and an intra-team role (`MANAGER` / `LEAD` / `MEMBER`) for task delegation.
- **A rich task lifecycle**: five canonical statuses (`PENDING`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `CANCELLED`), an orthogonal `is_blocked` flag, directed relations (`BLOCKS`, `MITIGATES`, `DUPLICATES`, `RELATES_TO`), cross-team work requests with leadership-gated fulfillment, append-only activity logs, comments with mentions, and per-task ratings.
- **Agents as members** with their own scoped JWT (`scope='agent'`, 15-minute TTL) issued by exchanging an API key. Keys are admin-issued, HMAC-hashed at rest, soft-revocable, and carry an env tag that prevents cross-environment misuse.
- **An internal admin panel** for cross-tenant operator intervention, sealed behind a six-layer zero-trust topology.

The codebase is an Nx-managed monorepo: a FastAPI service (Python 3.12, SQLAlchemy 2.x async, Alembic) backed by PostgreSQL 15, plus three Next.js 14 applications (marketing site, SaaS dashboard, admin panel). Everything ships to Google Cloud Platform via Cloud Run, fronted by a global HTTPS load balancer with Cloud Armor at the edge, and provisioned end-to-end with OpenTofu through a Workload-Identity-Federation-authenticated GitHub Actions pipeline.

---

## Architecture

### System diagram

```mermaid
flowchart LR
    subgraph Internet
        U[Browser / external integrator]
    end

    subgraph Edge["Google Cloud edge"]
        LB["HTTPS Load Balancer<br/>kanea-url-map"]
        CA["Cloud Armor<br/>(OWASP rules + per-IP rate ban)"]
        LB --- CA
    end

    subgraph Routing["Host-based URL map"]
        H1["kanea.ai / www.kanea.ai → www"]
        H2["app.kanea.ai → web-app"]
        H3["admin.kanea.ai → admin-panel<br/>(IAP-gated)"]
        H4["/api/* on every host → api"]
    end

    subgraph CloudRun["Cloud Run services<br/>(europe-west1)"]
        WWW["www<br/>(Next.js 14)"]
        WEB["web-app<br/>(Next.js 14)"]
        ADM["admin-panel<br/>(Next.js 14)<br/>ingress=internal-LB-only"]
        API["api<br/>(FastAPI · Python 3.12)"]
    end

    subgraph Data["Private services VPC"]
        SQL[("Cloud SQL Postgres 15<br/>private IP only")]
        SM[("Secret Manager<br/>db_url · oauth · agent_api_key_pepper")]
    end

    U --> CA --> LB
    LB --> H1 --> WWW
    LB --> H2 --> WEB
    LB --> H3
    H3 -. "IAP at LB edge:<br/>roles/iap.httpsResourceAccessor<br/>on engineering@kanea.ai" .-> ADM
    LB --> H4 --> API
    API -- VPC connector --> SQL
    API -- secret_key_ref --> SM
```

> _Diagram is conceptual — it illustrates the request path and the trust layers, not the literal 1:1 of `infra/opentofu/`. The OpenTofu codebase under `infra/opentofu/` is the source of truth for resource names, IAM bindings, and routing rules. Portable exports: [`docs/architecture-diagram.svg`](docs/architecture-diagram.svg), [`docs/architecture-diagram.png`](docs/architecture-diagram.png); source: [`docs/architecture-diagram.mmd`](docs/architecture-diagram.mmd)._

### Repository layout

```
kanea-monorepo/
├── apps/
│   ├── api/            # FastAPI service (Python 3.12, Poetry, SQLAlchemy 2.x async)
│   ├── web-app/        # SaaS dashboard          (Next.js 14, App Router) — port 3000
│   ├── www/            # Marketing landing site  (Next.js 14)             — port 3001
│   └── admin-panel/    # Internal back-office    (Next.js 14)             — port 3002
├── docs/               # Architecture diagram source + exports
├── infra/
│   └── opentofu/       # GCP infrastructure as code (Cloud Run, Cloud SQL, LB, WIF, …)
├── .github/workflows/  # pr-checks.yml (CI) and deploy.yml (CD)
├── docker-compose.local.yml  # Local Postgres 15 for development
├── nx.json
├── pnpm-workspace.yaml
└── tsconfig.base.json
```

| Path               | Purpose                                                                                                                 |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `apps/api`         | Hexagonal FastAPI service. Owns all data access, business logic, RBAC, auth, and Alembic migrations.                    |
| `apps/web-app`     | The tenant-facing dashboard. Kanban board, projects, blocks, directory, audit, profile.                                 |
| `apps/www`         | The public marketing site at `kanea.ai` / `www.kanea.ai`.                                                               |
| `apps/admin-panel` | Cross-tenant operator console for internal Kanea staff. Sealed behind IAP.                                              |
| `infra/opentofu`   | OpenTofu codebase for both prod (`main` branch) and staging (`dev` branch). Single state bucket, env-suffixed prefixes. |

### Backend stack

The api follows a hexagonal layout — the `app/api/v1/*.py` routers are thin and delegate to `app/application/<domain>/service.py`, which owns the business logic and depends only on `Protocol`-typed ports in `app/application/<domain>/ports.py`. SQLAlchemy implementations of those ports live under `app/infrastructure/repositories/`. This keeps the service layer pure and unit-testable against in-memory SQLite or simple mocks, while the integration suite exercises real Postgres via a separate fixture.

| Layer         | Tech                                                                                                    |
| ------------- | ------------------------------------------------------------------------------------------------------- |
| Web framework | FastAPI 0.115, Pydantic v2, asyncio end-to-end                                                          |
| Persistence   | SQLAlchemy 2.x async ORM, `asyncpg` driver, Alembic migrations                                          |
| Auth          | PyJWT (HS256), bcrypt password hashing, HMAC-SHA-256 for agent keys                                     |
| Local data    | PostgreSQL 15 (Docker container for dev)                                                                |
| Frontends     | Next.js 14 App Router, React 18, TanStack Query 5, Tailwind CSS, Vitest + Testing Library (admin-panel) |
| Monorepo      | Nx 20, pnpm 9, Poetry (Python deps)                                                                     |

### GCP topology

All infrastructure is declared in `infra/opentofu/`. Both environments share the same project (`kanea-prod-env`) and OpenTofu state bucket; staging resources get a `-staging` name suffix via `local.name_suffix` so the two states coexist without collision (see `infra/opentofu/locals.tf`).

**Edge.** A single global HTTPS load balancer (`google_compute_url_map.main`) terminates TLS using Google-managed certificates for `kanea.ai`, `www.kanea.ai`, `app.kanea.ai`, and `admin.kanea.ai`. The URL map dispatches by host:

```
kanea.ai / www.kanea.ai → backend "www"
app.kanea.ai            → backend "web-app"
admin.kanea.ai          → backend "admin-panel"  (IAP-protected)
*  + /api/*             → backend "api"
```

Cloud Armor sits in front of the LB. In prod (`infra/opentofu/cloudarmor.tf`), the policy enables the pre-configured OWASP rule set (SQLi, XSS, LFI, RCE, scanners, protocol attacks, session-fixation), a per-IP rate-based ban, an explicit allow for the OAuth-callback path matching `^/api/v1/auth/oauth/[^/]+/callback` so legitimate IdP redirects aren't caught by the WAF, and a default `allow` for everything else. Staging swaps in a simpler default-deny + IP-allowlist policy.

**Compute.** Four Cloud Run v2 services in `europe-west1` (`infra/opentofu/cloudrun.tf`): `api`, `web-app`, `www`, `admin-panel`. The three public services have `roles/run.invoker` granted to `allUsers` (so the LB can reach them); the admin-panel has `ingress = INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` and `roles/run.invoker` scoped only to the IAP Service Agent, so anything that bypasses both IAP and the LB ingress check still gets refused by Cloud Run IAM.

**Data.** A regional Cloud SQL Postgres 15 instance with Private Service Access (`infra/opentofu/cloudsql.tf` + `network.tf`). The instance has no public IP; the api reaches it over the VPC peering established by `google_service_networking_connection.private_vpc`. Connection strings, OAuth client secrets, and the agent API-key pepper all live in GCP Secret Manager and are mounted into the api via `secret_key_ref` env bindings.

**Auth for CI.** Workload Identity Federation (`infra/opentofu/wif.tf`) lets GitHub Actions impersonate the `github-deployer` service account via OIDC. No SA JSON keys live in repo secrets.

---

## Admin Panel zero-trust security

The admin panel (`admin.kanea.ai`) is the operator surface for cross-tenant intervention — banning a user, suspending a workspace, editing any agent in any workspace. Its threat model is "an attacker who has somehow obtained credentials for one Kanea engineer should still be refused if they are not the _right_ engineer." Six independent gates layer to enforce that. Each is verified against code below.

| Layer                             | Mechanism                                                                                                                                                                                                                                                                                                                                                               | Verified at                                                                                             |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **1. DNS**                        | The `admin.kanea.ai` hostname only resolves to the Kanea LB. Not strictly an access control, but it ensures every other layer is on the request path.                                                                                                                                                                                                                   | `google_compute_managed_ssl_certificate.admin` in `infra/opentofu/loadbalancer.tf`                      |
| **2. IAP at the LB edge**         | A request without a valid IAP cookie / token is bounced to a Google sign-in screen. The backend service for `admin-panel` has IAP enabled via a `dynamic "iap"` block, sourcing OAuth client creds from Secret Manager (the brand is "External", which prohibits Tofu-managed `google_iap_client`, so the client was created manually and referenced via data sources). | `infra/opentofu/loadbalancer.tf` lines 41–57 + `infra/opentofu/iap.tf`                                  |
| **3. IAP IAM allow-list**         | Even after sign-in, IAP checks `roles/iap.httpsResourceAccessor` on the IAP-protected backend. Membership is bound to `group:engineering@kanea.ai`; anyone not in that group gets a 403 here.                                                                                                                                                                           | `google_iap_web_backend_service_iam_member.admin_panel_accessor` in `infra/opentofu/iap.tf`             |
| **4. Internal-LB-only ingress**   | The Cloud Run service is marked `ingress = INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`. Direct hits to the auto-generated `*.run.app` URL are refused at Cloud Run's frontend before the container is ever invoked.                                                                                                                                                         | `infra/opentofu/cloudrun.tf:28`                                                                         |
| **5. IAP-only invoker**           | `roles/run.invoker` on the admin-panel service is bound only to the IAP Service Agent (`service-{project-number}@gcp-sa-iap.iam.gserviceaccount.com`), not to `allUsers`. Requests that somehow bypass both IAP and the ingress check still get rejected by Cloud Run IAM.                                                                                              | `google_cloud_run_v2_service_iam_member.admin_panel_invoker` in `infra/opentofu/cloudrun.tf:208`        |
| **6. App-layer superadmin check** | Every route under `/api/v1/admin/*` depends on `SuperadminDep`, which requires `users.is_superadmin = true` on the calling JWT's user. The flag has no API endpoint that can flip it — only the CLI script `apps/api/scripts/make_superadmin.py` (run by an operator with DB access) can elevate.                                                                       | `app/api/deps.py:643` for `SuperadminDep`; `apps/api/scripts/make_superadmin.py` for the bootstrap path |

The layers are independent on purpose: revoking an engineer's `engineering@kanea.ai` membership locks them out at layer 3 without touching anything else; revoking their `is_superadmin` flag locks them out at layer 6 even if IAP would still let them through. Compromise of any single layer is insufficient.

---

## Data model & RBAC

### Tenancy

Every user-supplied row carries a `workspace_id`. Every route that reads or writes tenant data does so through the workspace-scoped JWT principal, which is verified against the row before any service code runs. The architecture is multi-tenant single-database: rows from different workspaces share tables but are filtered by `workspace_id` at every layer, with FK constraints (`ON DELETE CASCADE` from `workspaces`) keeping the topology clean.

### The user / agent distinction

A `users` row is the global human identity — one per email across all workspaces. A `members` row is the per-workspace projection of that identity. AGENT members have no `users` row at all (CHECK constraint on `members`: `HUMAN ⇒ user_id NOT NULL, AGENT ⇒ user_id NULL`). Auth credentials live in two places:

- `credentials` table: per-HUMAN auth (password hash and/or OAuth identity). AGENT members never have a row here.
- `agent_api_keys` table: per-key HMAC digests for AGENT members. N keys per agent, soft-revocable, with per-key `last_used_at`. See [Agent integration](#agent-integration--api-key-lifecycle) for the full lifecycle.

This split means a human can sign in to multiple workspaces with a single password / OAuth identity, while an agent's identity is rigorously scoped: its API key proves it is _this_ agent in _this_ workspace, nothing more.

### Workspace roles + priority

The workspace-level role (`MemberRole` enum in `app/domain/enums.py`) is one of `WORKSPACE_OWNER`, `WORKSPACE_ADMIN`, `WORKSPACE_USER`. The intent: `OWNER` runs the tenant, `ADMIN` administers without ownership-only operations, `USER` participates without administrative reach.

Layered on top is the **priority** field (`int`, 1..100, default 5; 1 = highest). Priority is the actual gate for many administrative endpoints, not the role alone. The dependency `require_admin_priority_le(N)` in `app/api/deps.py:737` produces a `WorkspaceAdminDep`-like requirement that demands an admin role _and_ a priority numerically ≤ N. As a result:

- A `WORKSPACE_ADMIN` with `priority=1` (effectively the workspace's co-owner) can edit departments.
- A `WORKSPACE_ADMIN` with `priority=3` can edit teams but not departments.
- A `WORKSPACE_USER` regardless of priority cannot touch either.

The same priority drives delegation: a member can delegate a task to anyone with a priority ≥ theirs (i.e., equal or lower rank). The reach checks live in `app/application/tasks/service.py`.

### Department-Head isolation rule

A department's `head_id` (column on `departments`, with a unique partial index ensuring at most one membership) appoints exactly one HUMAN member as the head. The Round-2 isolation rule, enforced both at the service layer and by the unique partial index, says:

- A head's `team_id` is forced NULL — heads cannot also sit on a team.
- A member with a non-NULL `team_id` cannot be promoted to head — they must vacate the team first.
- The backend's `DepartmentService.update` orchestrates the transitions transactionally (clear team → set head) so the intermediate state never persists.

### One MANAGER / one LEAD per team, with auto-demotion

A team has at most one `MANAGER` and at most one `LEAD` at any time, enforced by a unique partial index on `(team_id, team_role) WHERE team_role IN ('MANAGER','LEAD')`. When `InviteService.set_member_team` promotes a member to MANAGER on a team that already has one, the previous MANAGER is auto-demoted to MEMBER in the same transaction. The UI surfaces this as a warning: "Team already has a MANAGER (Alice). Confirm to demote them to MEMBER in the same transaction." Both the web-app's `RoleReplacementConfirm` component and the admin-panel's unified entity detail panel implement this flow.

### Unified entity detail / edit surface

The admin panel collapses every cross-tenant editor into a single `EntityDetailPanel` (`apps/admin-panel/app/components/EntityDetailPanel.tsx`). Opening a row from any list — `/users`, `/workspaces/[id]` — produces the same superset of sections:

- Identity header (name, email, type pill, badges for Superadmin / Banned / Suspended)
- Global section (humans only): workspace memberships, global ban with typed-email confirmation, force password reset with simulated-email preview
- Profile editor: `workspace_role`, `priority`
- Hierarchy editor: team + team_role + dept-head with the sitting-MANAGER warning
- Activity stats card: assigned / completed / avg resolution / accuracy / tokens / last activity

Agents are first-class here — they appear in the unified `/users` list with a Type column, and clicking them opens the same panel (minus the human-only sections, since agents have no global user). A member-id-keyed `PATCH /admin/workspaces/{ws}/members/{member_id}` endpoint replaces the user-id-keyed sibling for any intervention that needs to reach an agent.

### Audit log

Every administrative org-event lands in `audit_logs` (append-only). The visibility rule is hierarchical: `WORKSPACE ⊃ DEPARTMENT ⊃ TEAM ⊃ MEMBER`. An OWNER sees every row; a Priority-2 admin sees department/team/member; a Priority-3 admin only sees team rows for teams they oversee (HEAD/MANAGER/LEAD). The actor name in each row is itself clickable, opening the priority-scoped profile dialog.

---

## Core features

### Kanban board

The `/board` view in the web-app (`apps/web-app/app/(authed)/board/page.tsx`) is the primary planning surface. Tasks are grouped by `TaskStatus`: `PENDING`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `CANCELLED`. `IN_REVIEW` is the slot for work the executor considers done but that needs verification — QA, secondary-agent check, reviewer sign-off — sitting between `IN_PROGRESS` and `DONE`. The `is_blocked` flag is orthogonal: a task can be in `IN_PROGRESS` _and_ blocked, surfaced as a red overlay on the card.

Columns are individually collapsible. During drag, an empty or collapsed column auto-expands as the dragged card crosses its rail, then collapses again on drag-leave; the hit-test logic was tuned across several iterations to stay accurate while columns animate.

### Cross-team collaboration

A team that needs another team's output opens a task request (`task_requests`). The request lands in the target team's inbox (`/teams/{id}/requests`) and can only be fulfilled or rejected by a team-leadership member — `MANAGER`, `LEAD`, or the department head. Fulfilling the request mints a target task on the target team and links the two via a `BLOCKS` task relation, so the source task automatically shows the new dependency in its blocked-by panel. Cross-team requests can also auto-fulfill in specific scenarios when the originating team's leadership is also the target team's leadership.

### Append-only activity stream

Every state-changing operation on a task writes a row into `task_activities`. The vocabulary lives in `TaskActivityType` and currently covers: `CREATED`, `STATUS_CHANGED`, `ASSIGNED`, `DELEGATED`, `BLOCKED`, `UNBLOCKED`, `PROJECT_CHANGED`, `TEAM_CHANGED`, `RATED`, `PRIORITY_CHANGED`. Each row carries a JSONB payload with the transition's specifics (e.g. `{from, to}` for status changes).

`GET /api/v1/tasks/{id}/activity` returns the chronological feed merged with comments. The same endpoint at the project level (`GET /api/v1/projects/{id}/history`) aggregates across tasks. This stream is the canonical artifact an AI agent reads when reconstructing context, and the platform deliberately makes it the source of truth — there is no separate "agent context" store to drift from.

### Entity navigation mesh

A consistent navigation pattern across the web-app: any clickable name of a user, team, department, or project lands you on that entity's detail dialog or drawer. URL helpers in `apps/web-app/app/lib/links.ts` centralise the routing (deep-linking is `/directory?member=<id>`, `/teams?open=<id>`, `/departments?open=<id>`), so a future move to dedicated routes is a one-file diff. Audit log actor names, task assignees, blocked-by lists, and the department / team membership tables all use the same helpers.

### Notifications

Mentions in comments and task fields land in the `notifications` table and surface in the sidebar bell (`GET /api/v1/me/notifications`, `GET /api/v1/me/notifications/unread-count`). The current vocabulary is `MENTION_TASK` and `MENTION_COMMENT`; the schema is JSONB-payload so adding new types (assignments, blocked alerts) is an enum-only change.

---

## Agent integration & API-key lifecycle

This section documents the agent-auth flow as currently shipped. It is the recommended path for any external developer integrating an AI agent (including a Claude Code agent) against Kanea.

### Conceptual model

An **agent** is a `MemberModel` row with `type='AGENT'` and `user_id=NULL`. It belongs to exactly one workspace. Its identity is proved by an **API key**, which is admin-issued and admin-revocable. The agent never exchanges its API key directly with platform endpoints; instead, it exchanges the key for a short-lived **agent JWT** (`scope='agent'`, 15-minute TTL), which it then presents on every subsequent call.

### Key format

```
kna_<env>_<43-char base64url body>
```

- `kna` — stable family prefix ("Kanea Agent"). Greppable for ops and incident response.
- `<env>` — `live` on production, `dev` everywhere else. The api refuses any key whose env tag doesn't match its own `AGENT_API_KEY_ENV_TAG` setting — a `live` key handed to a dev API 401s with no DB round-trip and no HMAC compute (security property pinned by `tests/agents/test_agent_api_keys_primitives.py::test_malformed_and_cross_env_short_circuit_before_hmac`).
- `<body>` — `secrets.token_urlsafe(32)` → 43 characters of `[A-Za-z0-9_-]`, ~256 bits of CSPRNG entropy.

### At-rest representation

Only an **HMAC-SHA-256 digest** of the body is persisted, hex-encoded in `agent_api_keys.secret_hash`. The HMAC key is an operator-supplied **pepper** held in GCP Secret Manager (`agent-api-key-pepper`) and mounted into the api via `secret_key_ref` from Cloud Run. The pepper never appears in the repo, Tofu state, plan output, or any application log. A DB-only compromise cannot verify guessed or leaked key bodies without also stealing the pepper.

Two unhashed fields exist in `agent_api_keys` for operator UX:

- `prefix` — the literal `kna_<env>_` so the UI can fingerprint a key as `kna_live_…AbCd`.
- `last4` — the last four characters of the body, same purpose.

These are display-only and are never used for authentication.

### Endpoints

All paths under `/api/v1`. Issuance, listing, and revocation are admin-gated (workspace owner or admin). The exchange endpoint is public — it only requires presenting a valid key.

| Method | Path                                   | Auth                | Purpose                                                                                                                                                                    |
| ------ | -------------------------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/agents`                              | `WorkspaceAdminDep` | Provision an agent and mint a first API key. Returns `api_key` plaintext exactly once.                                                                                     |
| POST   | `/agents/{agent_id}/api-keys`          | `WorkspaceAdminDep` | Mint an additional key for an existing agent. Body: `{ label?: string }`. Returns `api_key` plaintext exactly once plus the fingerprint (`prefix`, `last4`, `created_at`). |
| GET    | `/agents/{agent_id}/api-keys`          | `WorkspaceAdminDep` | Inventory listing. Metadata only — no plaintext, no hash. Includes `last_used_at` and `revoked_at`.                                                                        |
| DELETE | `/agents/{agent_id}/api-keys/{key_id}` | `WorkspaceAdminDep` | Soft-revoke. Sets `revoked_at`. Idempotent — re-revoking returns 204 and does nothing.                                                                                     |
| POST   | `/auth/agent-token`                    | Public              | Exchange `{ api_key }` for a scope-`agent` JWT (`expires_in: 900`).                                                                                                        |

### Exchange path (server-side)

1. The body of the supplied `api_key` is split off from `kna_<env>_`.
2. The env tag is checked against `AGENT_API_KEY_ENV_TAG`. Mismatch → 401 with no further work.
3. The body is HMAC-SHA-256'd with the pepper.
4. The api looks up `agent_api_keys` by `secret_hash` with `revoked_at IS NULL`. Miss → 401.
5. The agent's member row is loaded. If the member is missing, has been hard-deleted, or is somehow not of type `AGENT`, 401.
6. The exchange stamps `last_used_at` on the key row and `last_seen_at` on the member row in the same transaction (the "free heartbeat" side-effect — agents that exchange regularly stay `ONLINE` in the UI even if they never call `/agents/me/heartbeat` explicitly).
7. A JWT with `scope='agent'`, the agent's `workspace_id`, `priority`, and the agent's member id as `sub` is issued. TTL: 900 seconds (`settings.jwt_agent_ttl_seconds`).

Every failure mode returns the same generic `{"detail":"invalid agent credentials"}` so an attacker cannot distinguish malformed, wrong-env, unknown, revoked, or pointing-at-a-deleted-agent.

### Rotation

Routine rotation does not require an infrastructure change. The procedure is **mint → swap → revoke**:

1. Mint a new key via `POST /agents/{id}/api-keys`.
2. Reconfigure the agent to use the new key. Both keys are valid in this window.
3. Confirm the new key's `last_used_at` is advancing (`GET /agents/{id}/api-keys`).
4. Revoke the old key via `DELETE /agents/{id}/api-keys/{old_key_id}`. Subsequent exchanges with it 401.

Pepper rotation (changing the HMAC key for the whole environment) is a different operation: see [Operations & runbook](#operations--runbook).

### Quickstart — pointing a Claude Code agent at Kanea

This walks an external developer through the full provisioning + integration flow. All commands assume `prod`; substitute the staging URL and a `kna_dev_…` key if you're targeting staging.

**Prerequisites:**

- A Kanea workspace where you have `WORKSPACE_OWNER` or `WORKSPACE_ADMIN` role.
- A workspace-scoped JWT for that account. The simplest way: sign in to `https://app.kanea.ai`, then in DevTools read the `kanea_token` value from `localStorage` (this is the literal key declared as `TOKEN_STORAGE_KEY` in `apps/web-app/app/lib/api.ts`). Export it as `$JWT` in your shell.

**Step 1 — provision the agent and capture its first API key.**

```bash
JWT="<your-workspace-admin-jwt>"

# Mints an AGENT member in your workspace and returns its first API key
# in plaintext. The plaintext is shown exactly once; the hash that lands
# in the DB is HMAC-SHA-256 of the body under the server-side pepper.
curl -s -X POST https://app.kanea.ai/api/v1/agents \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"claude-code-runner","priority":5,"model":"claude-opus-4-7"}' \
  | tee /dev/tty \
  | jq -r .api_key > ~/.kanea/agent.key

chmod 600 ~/.kanea/agent.key
# The id field in the response is the agent's member_id — record it
# alongside the key. Subsequent admin operations (listing keys, revoking,
# minting additional keys) are keyed by this id.
```

The returned shape:

```json
{
  "id": "<agent-member-uuid>",
  "workspace_id": "<workspace-uuid>",
  "name": "claude-code-runner",
  "priority": 5,
  "model": "claude-opus-4-7",
  "api_key": "kna_live_AbCdEf...43_chars..." // pragma: allowlist secret
}
```

**Step 2 — exchange the key for an agent JWT.**

The agent does this on startup and again every ~14 minutes (the JWT expires at 15).

```bash
API_KEY=$(cat ~/.kanea/agent.key)

curl -s -X POST https://app.kanea.ai/api/v1/auth/agent-token \
  -H "Content-Type: application/json" \
  -d "{\"api_key\":\"$API_KEY\"}" \
  | jq -r .access_token > ~/.kanea/agent.jwt
```

Response shape: `{ "access_token": "...", "token_type": "bearer", "expires_in": 900 }`.

**Step 3 — present the JWT on subsequent calls.**

```bash
AGENT_JWT=$(cat ~/.kanea/agent.jwt)

# Stamp last_seen_at (also happens for free on exchange, but explicit
# heartbeats can be useful during long-running operations between
# token refreshes).
curl -s -X POST https://app.kanea.ai/api/v1/agents/me/heartbeat \
  -H "Authorization: Bearer $AGENT_JWT" -i

# List tasks assigned to this agent.
curl -s https://app.kanea.ai/api/v1/tasks?assignee_id=<this-agent-id> \
  -H "Authorization: Bearer $AGENT_JWT" | jq .

# Move a task into IN_REVIEW.
curl -s -X PATCH https://app.kanea.ai/api/v1/tasks/<task-id>/status \
  -H "Authorization: Bearer $AGENT_JWT" \
  -H "Content-Type: application/json" \
  -d '{"status":"IN_REVIEW"}'

# Read the full activity history of a task (for context reconstruction).
curl -s https://app.kanea.ai/api/v1/tasks/<task-id>/activity \
  -H "Authorization: Bearer $AGENT_JWT" | jq .
```

**Step 4 — handle JWT expiry.**

Treat any `401 invalid or expired token` from the api as a signal to re-exchange the API key. A robust agent loop wraps every call in: "if 401, exchange API key, retry once."

**Recommended hygiene:**

- Store the API key in a 0600 file (or your platform's secret store), never in source control.
- Issue a separate API key per environment / per agent instance. Revoke them independently when the agent is decommissioned or its host changes.
- Use the `label` field (`POST /agents/{id}/api-keys` body) to record where each key is deployed: `"github-runner"`, `"laptop-jordi"`, etc.

---

## Local development

The inner loop runs apps directly on the host so Next.js HMR and `uvicorn --reload` work normally. Only Postgres lives in Docker.

### Prerequisites

- **Node.js** ≥ 20.11
- **pnpm** ≥ 9 (enable via `corepack enable && corepack prepare pnpm@9.12.0 --activate`)
- **Python** 3.12 exactly. The repo pins `~3.12` because some C extensions (greenlet) lag on newer minors; avoid 3.13 / 3.14 here.
- **Poetry** ≥ 1.8
- **Docker** (for the local Postgres container)
- **pre-commit** (`pipx install pre-commit`)
- **OpenTofu** ≥ 1.8 (only if you intend to run `tofu plan` locally; not required for app dev)

### Install

```bash
# Workspace + Python deps
pnpm install
(cd apps/api && poetry env use python3.12 && poetry install)

# Git hooks (ruff, black, prettier, detect-secrets)
pre-commit install
```

### Environment variables

Each app reads its config from per-app `.env` files. Committed `.env.development` files carry shared dev defaults that work against the Dockerised Postgres out of the box. Personal overrides go in `.env` (gitignored) and take precedence.

| File                                                    | Status     | Purpose                                  |
| ------------------------------------------------------- | ---------- | ---------------------------------------- |
| `apps/api/.env.development`                             | committed  | Shared API dev defaults                  |
| `apps/api/.env`                                         | gitignored | Personal API overrides (wins)            |
| `apps/api/.env.example`                                 | committed  | Template listing every required variable |
| `apps/{web-app,www,admin-panel}/.env.development`       | committed  | Shared frontend dev defaults             |
| `apps/{web-app,www,admin-panel}/.env.development.local` | gitignored | Personal frontend overrides (wins)       |

The notable api variables, all backed by `apps/api/app/core/config.py`:

| Variable                                                | Field on `Settings`                                                                                             | Dev default                    | Production source                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ENVIRONMENT`                                           | `environment: Environment` (no default; `Environment = Literal["development", "staging", "production"]`)        | required at construction time  | Required field — pydantic refuses to construct `Settings` when `ENVIRONMENT` is unset or invalid, BEFORE the model validator runs. Local dev gets it from `.env.development` (sets `ENVIRONMENT=development`); CI's pytest job picks up the same file from `apps/api/`; prod / staging Cloud Run set it explicitly via `infra/opentofu/cloudrun.tf`. A future deploy that forgets the binding crashes on import rather than silently no-op'ing every prod-only validator. Drives the [unified secrets validator](#operations--runbook). |
| `DATABASE_URL`                                          | `database_url: str = "postgresql+asyncpg://kanea:kanea@localhost:5432/kanea"` <!-- pragma: allowlist secret --> | the localhost DSN above        | Composed from Cloud SQL private IP, mounted from Secret Manager (`kanea-db-url`).                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `JWT_SECRET`                                            | `jwt_secret: str = "change-me-in-production"`                                                                   | the placeholder above          | Mounted from Secret Manager (`jwt-secret`) via `secret_key_ref` on the api Cloud Run service. In any `ENVIRONMENT` other than `development`, the api **refuses to start** if the value is still the committed placeholder — enforced by the unified `_check_required_secrets_in_prod` validator in `app/core/config.py`. The same secret signs and verifies every JWT (human / agent / selection / OAuth onboarding), so rotation invalidates every active session atomically; see [Operations & runbook](#operations--runbook).        |
| `JWT_HUMAN_TTL_SECONDS`                                 | `jwt_human_ttl_seconds: int = 3600`                                                                             | `3600` (1h)                    | Not set in `cloudrun.tf` — the Settings default applies.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `JWT_AGENT_TTL_SECONDS`                                 | `jwt_agent_ttl_seconds: int = 900`                                                                              | `900` (15m)                    | Not set in `cloudrun.tf` — the Settings default applies.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `AGENT_API_KEY_PEPPER`                                  | `agent_api_key_pepper: str = "change-me-in-production-agent-pepper"`                                            | the placeholder above          | Mounted from Secret Manager (`agent-api-key-pepper`) via `secret_key_ref` on the api Cloud Run service. In any `ENVIRONMENT` other than `development`, the api **refuses to start** if the value is still the committed placeholder — enforced by the unified `_check_required_secrets_in_prod` validator in `app/core/config.py`. The dev placeholder lets local dev boot without any pepper provisioning; never use it for anything that mints real keys.                                                                             |
| `AGENT_API_KEY_ENV_TAG`                                 | `agent_api_key_env_tag: str = "dev"`                                                                            | `dev`                          | `live` in prod, `dev` in staging. Embedded in minted keys' `kna_<env>_` prefix; the exchange refuses cross-env keys.                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `CORS_ORIGINS`                                          | `cors_origins: list[str] = []`                                                                                  | `["http://localhost:3000", …]` | Not set in `cloudrun.tf`; the Settings default (empty list) applies. In prod this is the correct value: the LB serves the api and the web-app from the same origin, so no CORS preflight is triggered.                                                                                                                                                                                                                                                                                                                                  |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | `google_oauth_client_id: str = ""` / `google_oauth_client_secret: str = ""`                                     | empty (provider disabled)      | Plain env / Secret Manager.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` | analogous                                                                                                       | empty (provider disabled)      | Plain env / Secret Manager.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `OAUTH_POST_LOGIN_REDIRECT`                             | `oauth_post_login_redirect: str = "http://localhost:3000/auth/callback"`                                        | the dev URL above              | `https://app.kanea.ai/auth/callback` in prod.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `API_BASE_URL`                                          | `api_base_url: str = "http://localhost:8000"`                                                                   | the dev URL above              | `https://app.kanea.ai` in prod.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `COOKIE_SECURE`                                         | `cookie_secure: bool = False`                                                                                   | `false` (HTTP dev)             | `true` in prod (TLS terminates at the LB).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

### Database

```bash
pnpm dev:db          # Postgres 15-alpine on :5432 (data persists in named volume)
pnpm dev:migrate     # alembic upgrade head against the local DB

# Other DB helpers:
pnpm dev:db:logs     # follow Postgres logs
pnpm dev:db:stop     # stop container, data persists
pnpm dev:db:reset    # stop AND drop the volume — fresh DB on next start
```

### Run the stack

```bash
pnpm dev             # nx run-many -t dev — boots all 4 apps in parallel
```

Or one at a time:

```bash
nx run api:dev          # FastAPI on :8000 with --reload
nx run web-app:dev      # SaaS dashboard on :3000
nx run www:dev          # Marketing site on :3001
nx run admin-panel:dev  # Admin panel on :3002
```

Service URLs:

| URL                                  | App                |
| ------------------------------------ | ------------------ |
| `http://localhost:3000`              | `web-app` (SaaS)   |
| `http://localhost:3000/signup`       | Create a workspace |
| `http://localhost:3001`              | `www` (marketing)  |
| `http://localhost:3002`              | `admin-panel`      |
| `http://localhost:8000`              | FastAPI service    |
| `http://localhost:8000/docs`         | Swagger UI         |
| `http://localhost:8000/redoc`        | ReDoc              |
| `http://localhost:8000/openapi.json` | Raw OpenAPI        |

### Tests

```bash
# Backend — runs against in-memory SQLite by default. Integration tests
# (under tests/integration/) skip unless KANEA_TEST_DATABASE_URL is set.
cd apps/api
poetry run pytest                                         # unit suite

# Full suite incl. integration tests against a real local Postgres.
# (The DSN below is the documented local-dev value, not a credential.)
export KANEA_TEST_DATABASE_URL=postgresql+asyncpg://kanea:kanea@localhost:5432/kanea_test  # pragma: allowlist secret
poetry run pytest

# Frontend — admin-panel currently has the only configured runner (vitest).
cd apps/admin-panel
pnpm test
pnpm test:watch
```

The api enforces a **≥ 92% coverage gate** (`--cov-fail-under=92` in `apps/api/pyproject.toml`) on a curated include list (`apps/api/.coveragerc`), measured against the unit + integration suite combined.

### Common Nx commands

| Command                      | Purpose                                    |
| ---------------------------- | ------------------------------------------ |
| `pnpm dev`                   | Run every app's dev target in parallel     |
| `pnpm build`                 | Build all projects (Nx-cached)             |
| `pnpm lint`                  | Lint everything                            |
| `pnpm test`                  | Run all configured test targets            |
| `nx affected -t lint test`   | Lint + test only what changed since `main` |
| `nx graph`                   | Open the visual project graph              |
| `pnpm format`                | Prettier across the workspace              |
| `pre-commit run --all-files` | Run every hook locally                     |

---

## API reference

All routes are mounted under `/api/v1` by `apps/api/app/main.py`. Auth column:

- **public** — no JWT required
- **JWT** — any workspace-scoped human JWT
- **agent** — agent JWT (`scope='agent'`)
- **admin** — `WorkspaceAdminDep` (`WORKSPACE_OWNER` / `WORKSPACE_ADMIN`)
- **admin(P≤N)** — priority-gated admin
- **owner** — `WORKSPACE_OWNER`
- **superadmin** — platform `users.is_superadmin = true`

Plus `GET /health` outside the `/api/v1` prefix for Cloud Run probes.

### Authentication

| Method | Path                              | Auth              | Purpose                                                                                                             |
| ------ | --------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| POST   | `/auth/register`                  | public            | Self-service signup: provisions a User + Workspace + Owner member in one shot.                                      |
| POST   | `/auth/login`                     | public            | Email/password login. Returns access_token directly if 1 workspace, otherwise a selection_token + workspaces list.  |
| POST   | `/auth/select-workspace`          | selection token   | Exchange a selection_token + workspace_id for the final access_token.                                               |
| POST   | `/auth/switch-workspace`          | JWT               | Already-signed-in user reissues their JWT bound to a different workspace.                                           |
| POST   | `/auth/agent-token`               | public            | Exchange `{ api_key }` for a scope-`agent` JWT (15-min TTL).                                                        |
| GET    | `/auth/oauth/{provider}/login`    | public            | Begin OAuth flow (`google` or `github`). 302 to provider's authorize URL.                                           |
| GET    | `/auth/oauth/{provider}/callback` | public            | OAuth callback. Verifies state, exchanges code, returns either a JWT or an onboarding ticket for first-time signup. |
| POST   | `/auth/complete-oauth-onboarding` | onboarding ticket | Second leg of SSO signup. Caller supplies the workspace name the user picked.                                       |

### Self (`/me`)

| Method | Path                             | Auth | Purpose                                          |
| ------ | -------------------------------- | ---- | ------------------------------------------------ |
| GET    | `/me`                            | JWT  | Calling principal's profile.                     |
| PATCH  | `/me`                            | JWT  | Update own profile (name, etc.).                 |
| POST   | `/me/password`                   | JWT  | Change own password (requires current password). |
| GET    | `/me/stats`                      | JWT  | Own task stats (assigned, completed, etc.).      |
| GET    | `/me/notifications`              | JWT  | List notifications.                              |
| GET    | `/me/notifications/unread-count` | JWT  | Unread count for the sidebar bell.               |
| POST   | `/me/notifications/{id}/read`    | JWT  | Mark one notification read.                      |
| POST   | `/me/notifications/read-all`     | JWT  | Mark all notifications read.                     |
| GET    | `/me/workspaces`                 | JWT  | Workspaces the calling user belongs to.          |
| POST   | `/me/workspaces`                 | JWT  | Create a new workspace; caller becomes OWNER.    |
| GET    | `/me/dashboard`                  | JWT  | Role-scoped dashboard payload.                   |

### Workspaces, tenants, departments, teams, projects

| Method | Path                               | Auth       | Purpose                                                  |
| ------ | ---------------------------------- | ---------- | -------------------------------------------------------- |
| PATCH  | `/workspaces/{id}`                 | owner      | Rename a workspace.                                      |
| POST   | `/tenants/invites`                 | admin      | Create an invite.                                        |
| GET    | `/tenants/invites/{token}`         | public     | Anonymous invite preview.                                |
| POST   | `/tenants/invites/{token}/accept`  | public     | Accept an invite (auto-provisions a user row if needed). |
| GET    | `/tenants/members`                 | JWT        | Paginated member directory (visibility-scoped).          |
| GET    | `/tenants/members/{id}`            | JWT        | Single member.                                           |
| GET    | `/tenants/members/{id}/profile`    | JWT        | Priority-scoped profile (full vs limited).               |
| GET    | `/tenants/members/{id}/stats`      | JWT        | Per-member task stats.                                   |
| PATCH  | `/tenants/members/{id}`            | admin      | Edit name / workspace role / priority.                   |
| PATCH  | `/tenants/members/{id}/suspension` | admin      | Toggle workspace-scoped soft suspension.                 |
| PATCH  | `/tenants/members/{id}/team`       | admin      | Assign team + team_role.                                 |
| POST   | `/tenants/members/{id}/password`   | admin      | Admin-side password reset.                               |
| GET    | `/departments`                     | JWT        | List departments.                                        |
| POST   | `/departments`                     | admin(P≤2) | Create.                                                  |
| GET    | `/departments/{id}`                | JWT        | Read.                                                    |
| PATCH  | `/departments/{id}`                | admin      | Update name / description / head_id.                     |
| DELETE | `/departments/{id}`                | admin      | Delete.                                                  |
| GET    | `/teams`                           | JWT        | List teams.                                              |
| POST   | `/teams`                           | admin(P≤3) | Create.                                                  |
| PATCH  | `/teams/{id}`                      | admin      | Update.                                                  |
| DELETE | `/teams/{id}`                      | admin      | Delete.                                                  |
| GET    | `/projects`                        | JWT        | List.                                                    |
| POST   | `/projects`                        | JWT        | Create.                                                  |
| GET    | `/projects/{id}`                   | JWT        | Read.                                                    |
| PATCH  | `/projects/{id}`                   | JWT        | Update.                                                  |
| DELETE | `/projects/{id}`                   | JWT        | Delete.                                                  |
| GET    | `/projects/{id}/history`           | JWT        | Aggregated activity history across the project's tasks.  |
| GET    | `/projects/{id}/tasks`             | JWT        | Tasks in this project.                                   |

### Tasks, blocks, cross-team requests

| Method | Path                                  | Auth            | Purpose                                                                    |
| ------ | ------------------------------------- | --------------- | -------------------------------------------------------------------------- |
| GET    | `/tasks`                              | JWT             | List with filters / sort.                                                  |
| POST   | `/tasks`                              | JWT             | Create.                                                                    |
| GET    | `/tasks/{id}`                         | JWT             | Read.                                                                      |
| POST   | `/tasks/{id}/delegate`                | JWT             | Delegate to another member (priority-gated).                               |
| PATCH  | `/tasks/{id}/status`                  | JWT             | Change status.                                                             |
| PATCH  | `/tasks/{id}/links`                   | JWT             | Update project_id / team_id.                                               |
| PATCH  | `/tasks/{id}/priority`                | JWT             | Adjust priority.                                                           |
| PATCH  | `/tasks/{id}/block`                   | JWT             | Set / clear `is_blocked` with a reason.                                    |
| GET    | `/tasks/{id}/comments`                | JWT             | List comments.                                                             |
| POST   | `/tasks/{id}/comments`                | JWT             | Post a comment (supports `@`-mentions).                                    |
| GET    | `/tasks/{id}/activity`                | JWT             | Append-only activity log merged with comments.                             |
| GET    | `/tasks/{id}/relations`               | JWT             | List task relations.                                                       |
| POST   | `/tasks/{id}/relations`               | JWT             | Add a relation (`BLOCKS` / `MITIGATES` / `DUPLICATES` / `RELATES_TO`).     |
| DELETE | `/tasks/{id}/relations/{relation_id}` | JWT             | Remove a relation.                                                         |
| POST   | `/tasks/{id}/requests`                | JWT             | Open an outbound cross-team request from this task.                        |
| GET    | `/tasks/{id}/requests`                | JWT             | This task's outbound requests.                                             |
| POST   | `/tasks/{id}/rate`                    | JWT             | Rate a completed task (issuer-only, single-shot).                          |
| GET    | `/teams/{team_id}/requests`           | team leadership | Team's inbox of pending cross-team requests.                               |
| POST   | `/requests/{id}/fulfill`              | team leadership | Mint the target task + link with `BLOCKS`.                                 |
| POST   | `/requests/{id}/reject`               | team leadership | Reject with a reason.                                                      |
| GET    | `/blocks`                             | JWT             | Workspace-wide blocked tasks with sort (`PRIORITY` / `NEWEST` / `OLDEST`). |

### Agents

The exchange endpoint accepts only `{ api_key }`. There is no legacy `{ agent_id, secret }` shape.

| Method | Path                             | Auth  | Purpose                                                                             |
| ------ | -------------------------------- | ----- | ----------------------------------------------------------------------------------- |
| POST   | `/agents`                        | admin | Provision an agent + mint a first API key in one response.                          |
| GET    | `/agents`                        | JWT   | List agents in the workspace.                                                       |
| POST   | `/agents/me/heartbeat`           | agent | Agent self-pings `last_seen_at`. 403 for human callers.                             |
| GET    | `/agents/{id}`                   | JWT   | Agent detail with computed stats + health pill.                                     |
| PATCH  | `/agents/{id}`                   | admin | Edit name / priority / model.                                                       |
| DELETE | `/agents/{id}`                   | admin | Hard delete. 409 if the agent created tasks (FK RESTRICT on `tasks.created_by_id`). |
| POST   | `/agents/{id}/api-keys`          | admin | Mint an additional API key. Returns plaintext exactly once.                         |
| GET    | `/agents/{id}/api-keys`          | admin | Inventory listing. Metadata only — no plaintext, no hash.                           |
| DELETE | `/agents/{id}/api-keys/{key_id}` | admin | Soft-revoke. Idempotent.                                                            |

### Audit

| Method | Path          | Auth | Purpose                                                                     |
| ------ | ------------- | ---- | --------------------------------------------------------------------------- |
| GET    | `/audit/logs` | JWT  | List with hierarchical visibility (WORKSPACE ⊃ DEPARTMENT ⊃ TEAM ⊃ MEMBER). |

### Admin (cross-tenant — superadmin only)

| Method | Path                                               | Auth       | Purpose                                                                                                             |
| ------ | -------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------- |
| GET    | `/admin/health`                                    | superadmin | Liveness + caller-identity probe for the back-office.                                                               |
| GET    | `/admin/metrics`                                   | superadmin | Platform metrics (active workspaces, registered users, recent signups).                                             |
| GET    | `/admin/workspaces`                                | superadmin | Cross-tenant workspace listing.                                                                                     |
| PATCH  | `/admin/workspaces/{id}/suspend`                   | superadmin | Suspend / restore a workspace.                                                                                      |
| GET    | `/admin/workspaces/{id}`                           | superadmin | Workspace detail with stats.                                                                                        |
| GET    | `/admin/workspaces/{id}/users`                     | superadmin | Per-workspace member listing with hierarchy slot.                                                                   |
| PATCH  | `/admin/workspaces/{id}/users/{user_id}`           | superadmin | User-id-keyed hierarchy edit (humans only).                                                                         |
| PATCH  | `/admin/workspaces/{id}/members/{member_id}`       | superadmin | Member-id-keyed superset — works for humans and agents. Adds `workspace_role` + `priority` to the patchable fields. |
| GET    | `/admin/workspaces/{id}/members/{member_id}`       | superadmin | Single workspace-member fetch.                                                                                      |
| GET    | `/admin/workspaces/{id}/members/{member_id}/stats` | superadmin | Per-member task stats. Same shape for humans and agents.                                                            |
| GET    | `/admin/agents`                                    | superadmin | Cross-tenant agent listing for the unified `/users` page.                                                           |
| GET    | `/admin/users`                                     | superadmin | Cross-tenant user listing (humans).                                                                                 |
| GET    | `/admin/users/{id}`                                | superadmin | Global user detail with workspace memberships.                                                                      |
| POST   | `/admin/users/{id}/ban`                            | superadmin | Toggle platform ban.                                                                                                |
| POST   | `/admin/users/{id}/force-password-reset`           | superadmin | Randomise password + invalidate sessions.                                                                           |

For the full machine-readable contract, run the api locally and visit `http://localhost:8000/openapi.json`.

---

## CI/CD & deployment

### Pull-request checks — `.github/workflows/pr-checks.yml`

Every PR (and every push to `main`) runs:

1. **Pre-commit & Detect Secrets** — `ruff`, `black`, `prettier`, `detect-secrets`, plus the usual whitespace / large-file checks. Fails on any modification by a hook so reviewers see the actual final state.
2. **API tests (pytest)** — runs the full suite against a `postgres:16-alpine` service container with `KANEA_TEST_DATABASE_URL` pointing at it. The pipeline installs from `apps/api/requirements.txt` + `requirements-dev.txt` (the committed pip exports of Poetry's lockfile) to avoid Poetry-version mismatches in CI. **Enforces ≥ 92% coverage** on the curated include list in `apps/api/.coveragerc`.

### Deployment — `.github/workflows/deploy.yml`

Branch-to-env mapping is hard-coded:

| Branch | Target environment | Public domain                                                                                                                                                                                                   |
| ------ | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main` | **prod**           | `kanea.ai` (plus the routed subdomains `www`, `app`, `admin`). From `infra/opentofu/envs/prod.tfvars`; used by `loadbalancer.tf` URL map host rules and managed-cert SAN list.                                  |
| `dev`  | **staging**        | `staging.kanea.ai`. From `infra/opentofu/envs/staging.tfvars:16` (`domain = "staging.kanea.ai"`), wired through `loadbalancer.tf:71,88,115` (host rules) and `loadbalancer.tf:136,148,164` (managed-cert SANs). |

Pipeline stages:

1. **plan** — resolves `target_env`, the image tag (commit SHA), and the OpenTofu state prefix. Backend prefix for prod stays at the historical path so existing state isn't moved; staging gets its own subdir.
2. **build** _(matrix: `api`, `web-app`, `www`, `admin-panel`)_ — multi-stage Docker builds pushed to Artifact Registry with registry-backed buildx cache.
3. **Tofu apply** — `tofu init` then `tofu apply` against `envs/{prod|staging}.tfvars`. Authenticates via Workload Identity Federation (no JSON keys in repo secrets).
4. **deploy** _(matrix)_ — `gcloud run services update --image=…` rolls each new image onto its Cloud Run service.

The pipeline uses concurrency keyed by branch so a newer push cancels any older in-flight deploy of the same branch, preventing two pipelines from racing the same env's Tofu state lock.

---

## Operations & runbook

### `ENVIRONMENT` is load-bearing

The api's `Settings` model in `app/core/config.py` defaults `environment` to `"development"`. Every prod-only validator on the model (currently the agent API-key pepper guard; more will follow) is gated on `environment != "development"`. **If `ENVIRONMENT` is not set on the Cloud Run service, those validators silently no-op even on prod.**

`infra/opentofu/cloudrun.tf` sets this env var explicitly per environment:

```
ENVIRONMENT = local.is_prod ? "production" : "staging"
```

Any new prod-only safety check added to `Settings` should rely on this being correctly set — and any new environment / project added to the deploy pipeline must include this binding before the api will refuse the placeholder pepper.

### The agent API-key pepper

The pepper is the HMAC key used to derive `agent_api_keys.secret_hash` from the body of each minted key. Its operational properties:

- **Storage** — GCP Secret Manager, secret name `agent-api-key-pepper` (prod) / `agent-api-key-pepper-staging`. Provisioned by `infra/opentofu/secrets.tf`.
- **Mount** — read by Cloud Run via `secret_key_ref` at boot, exposed to the api as the `AGENT_API_KEY_PEPPER` env var. The value never appears in the Cloud Run service spec, `gcloud run services describe` output, application logs, or Tofu state.
- **Tripwire** — if `ENVIRONMENT != "development"` _and_ the pepper is the committed placeholder, the api raises `ValueError` on import and the Cloud Run revision fails to become Ready. Cloud Run keeps traffic on the previous revision until the next successful boot.
- **Rotation** — **rotating or losing the pepper invalidates every existing agent API key.** Plaintext is never persisted, so there is no re-hash path. The procedure: mint new keys under the new pepper, hand them to operators, revoke the old keys, then `gcloud secrets versions add` the new pepper value. (Order: never rotate the pepper before the new keys are issued and validated, or every agent's exchange will 401.)
- **Initial provisioning** — see the [two-phase wiring](#two-phase-wiring-for-prod-only-secrets-pattern) below.

### Two-phase wiring for prod-only secrets (pattern)

A reusable pattern for any future secret whose absence trips a prod-only validator:

1. **Phase A** — Tofu creates the secret container with a placeholder version (`lifecycle.ignore_changes = [secret_data]`) and the IAM grant. **Nothing references the secret in the api Cloud Run service spec.** Apply changes nothing about how the api behaves.
2. **Operator step** — `gcloud secrets versions add` the real value into the now-existing container. Verify with `gcloud secrets versions list <secret> --format='value(name,state,createTime)'`: two ENABLED versions, the real one being the latest.
3. **Phase B** — Tofu adds the `secret_key_ref` env binding (and any related env vars, e.g. `ENVIRONMENT`). The new Cloud Run revision boots reading the real value on first try — no deliberate-failure window.

The two-PR split is mechanical: Phase B is opened as a GitHub **draft** PR so it cannot be merged before Phase A is applied + the real secret is in place. The draft state is the lock; the description is the explanation.

### Break-glass database access

The prod Cloud SQL Postgres instance has **no public IP** — it is only reachable from inside the VPC via Private Service Access. Direct `psql` from a laptop, or the `cloud-sql-proxy` from a workstation, will not work because the VPC is not laptop-accessible.

The supported path for one-off reads / break-glass writes is **Cloud SQL Studio in the Google Cloud Console**: sign in with a Google account that has `roles/cloudsql.admin` (or equivalent), open the instance, run queries through the browser. Authentication is the Google identity; queries land in Cloud SQL's audit log.

A VPC-connected programmatic path (e.g. `gcloud run jobs` against a throwaway image with `psql` and the VPC connector, or a temporary GCE VM in the same VPC) is _architecturally_ possible but is **not an established procedure** here — the team has not used it in practice. If a future need for non-interactive bulk reads or scripted maintenance arises, that path should be designed, documented, and rehearsed before being relied on.

Do **not** spend time trying to make `cloud-sql-proxy` work from a workstation against prod — by design, it cannot.

### Audit query: agent keys minted under a specific pepper window

If a pepper rotation is performed, or a suspected compromise is being investigated, this is the canonical query for identifying keys that exist in a particular time window:

```sql
SELECT k.id, k.member_id, k.prefix, k.last4, k.label,
       k.created_at, k.last_used_at, k.revoked_at,
       m.name AS agent_name, m.workspace_id
FROM agent_api_keys k
JOIN members m ON m.id = k.member_id
WHERE k.created_at >= '<window-start-iso>'
  AND (k.created_at < '<window-end-iso>' OR '<window-end-iso>' IS NULL)
ORDER BY k.created_at;
```

To revoke compromised keys without app access: set `revoked_at = now()` on the affected rows directly in Cloud SQL Studio. Subsequent exchanges of those keys will 401.

---

## Deployment models

Kanea today runs as a managed multi-tenant SaaS on Google Cloud Platform. The architecture is designed to support a future self-hosted deployment model alongside the managed cloud offering — the api itself is stateless and depends only on a Postgres database, a secret store, and a reverse proxy, all of which can be supplied by any sufficiently capable host. **Self-hosting is forward-looking intent, not a currently available product**: there is no published setup guide, no supported third-party operator path, and no licensing posture that permits it today (see [License](#license)). The intent is recorded here so the architectural shape of the platform is not later contradicted by a self-hosted offering: nothing in the codebase prevents a future source-available / managed-cloud split.

---

## Implementation history

This section maps notable capabilities to the GitHub PRs that introduced them, for traceability. The README's body deliberately describes features by what they are today, not by PR number — this is the single dedicated mapping table.

| Capability                                              | PR(s)   | What it introduced                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unified entity detail / edit surface in the admin panel | **#38** | The single `EntityDetailPanel` component. Member-id-keyed admin endpoints (`PATCH /admin/workspaces/{ws}/members/{member_id}`, the matching GET, and per-member stats). Cross-tenant agent listing at `GET /admin/agents`. Made agents first-class in the admin `/users` view via a Type column.                                                                                                                                   |
| Per-agent API keys, HMAC-pepper auth, soft-revoke       | **#39** | The `agent_api_keys` table (migration `0029`). `POST/GET/DELETE /agents/{id}/api-keys`. New `POST /auth/agent-token { api_key }` shape; removed the legacy `{ agent_id, secret }` exchange. Dropped `credentials.agent_secret_hash`. Tightened `POST /agents` to `WorkspaceAdminDep`. `kna_<env>_<body>` key format with env-tag enforcement. `Settings._check_pepper_set_in_prod` tripwire. Coverage gate raised from 90% to 92%. |
| Agent API-key pepper wiring (Phase A)                   | **#40** | Secret Manager container `agent-api-key-pepper` + secretAccessor IAM grant on `run-api`. Dormant: nothing references the secret yet, so the api Cloud Run service spec is unchanged.                                                                                                                                                                                                                                               |
| Agent API-key pepper wiring (Phase B)                   | **#41** | The `AGENT_API_KEY_PEPPER` `secret_key_ref` binding on the api Cloud Run service. `ENVIRONMENT=production` / `=staging`. `AGENT_API_KEY_ENV_TAG=live` / `=dev`. Armed the prod-only validators that had previously been silent no-ops because `ENVIRONMENT` was unset.                                                                                                                                                             |

---

## License

Proprietary. © Kanea. All rights reserved.
