"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse, register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging

API_V1_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Turns a recipe recording into a reviewed, SEO-friendly recipe blog.",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        responses={500: {"model": ErrorResponse, "description": "Unexpected server error."}},
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    # Added last so it wraps CORS and sees every request.
    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)

    app.include_router(api_router, prefix=API_V1_PREFIX)
    return app


app = create_app()
