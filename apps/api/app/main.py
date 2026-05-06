from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.tasks import router as tasks_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Mount under /api/v1 to match the public surface routed by the LB
# (`/api/*` → this service, no rewrite). Internal routers keep their own
# `/auth`, `/tasks` prefixes — so the public path is `/api/v1/auth/login`,
# `/api/v1/tasks`, etc., which is what the blueprint specifies.
API_V1_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(tasks_router, prefix=API_V1_PREFIX)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
