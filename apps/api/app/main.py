from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.agents import router as agents_router
from app.api.v1.auth import router as auth_router
from app.api.v1.me import router as me_router
from app.api.v1.projects import router as projects_router
from app.api.v1.requests import router as requests_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.teams import router as teams_router
from app.api.v1.tenants import router as tenants_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Cross-origin only matters during local dev — in prod the LB serves the
# api and the Next.js apps from the same origin, so the request is
# same-origin and never triggers a CORS preflight. settings.cors_origins
# is empty by default; populated via env in apps/api/.env.development.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount under /api/v1 to match the public surface routed by the LB
# (`/api/*` → this service, no rewrite). Internal routers keep their own
# `/auth`, `/tasks` prefixes — so the public path is `/api/v1/auth/login`,
# `/api/v1/tasks`, etc., which is what the blueprint specifies.
API_V1_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(tasks_router, prefix=API_V1_PREFIX)
app.include_router(tenants_router, prefix=API_V1_PREFIX)
app.include_router(agents_router, prefix=API_V1_PREFIX)
app.include_router(projects_router, prefix=API_V1_PREFIX)
app.include_router(teams_router, prefix=API_V1_PREFIX)
app.include_router(requests_router, prefix=API_V1_PREFIX)
app.include_router(me_router, prefix=API_V1_PREFIX)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
