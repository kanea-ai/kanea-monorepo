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

app.include_router(auth_router)
app.include_router(tasks_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
