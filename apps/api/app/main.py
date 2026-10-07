from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from repomedic_core.config import get_settings
from repomedic_core.db import init_db
from repomedic_core.logging import configure_logging, get_logger

from app.routers import health, tasks, webhooks

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    await init_db()
    logger.info("api_started", env=settings.app_env)
    yield
    logger.info("api_stopped")


app = FastAPI(
    title="RepoMedic API",
    description="Issue-to-Patch Software Engineering Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])