"""Liveness/readiness endpoint."""

import logging
from enum import StrEnum

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class ComponentStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class HealthResponse(BaseModel):
    status: HealthStatus
    version: str
    database: ComponentStatus


@router.get(
    "/health",
    summary="Service health",
    description=(
        "Reports the API version and whether the database is reachable. "
        "Returns 200 when healthy and 503 when a dependency is down."
    ),
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "A dependency is unavailable."}},
)
async def health(
    response: Response, session: AsyncSession = Depends(get_session)
) -> HealthResponse:
    database = ComponentStatus.OK
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("health_database_unreachable", exc_info=True)
        database = ComponentStatus.ERROR

    if database is ComponentStatus.OK:
        return HealthResponse(status=HealthStatus.OK, version=__version__, database=database)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status=HealthStatus.DEGRADED, version=__version__, database=database)
