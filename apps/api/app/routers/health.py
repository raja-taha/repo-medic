from fastapi import APIRouter

from repomedic_core import __version__
from repomedic_core.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="repomedic-api", version=__version__)