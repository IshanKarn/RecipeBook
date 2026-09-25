from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    ErrorCode,
    MediaValidationError,
    NotFoundError,
)
from app.main import create_app

pytestmark = pytest.mark.unit


class Payload(BaseModel):
    count: int


@pytest.fixture
def error_app(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/boom/not-found")
    async def not_found() -> None:
        raise NotFoundError("Recipe not found.")

    @app.get("/boom/conflict")
    async def conflict() -> None:
        raise ConflictError("Already processing.")

    @app.get("/boom/too-large")
    async def too_large() -> None:
        raise MediaValidationError("Audio is too large.", code=ErrorCode.FILE_TOO_LARGE)

    @app.get("/boom/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("secret internal detail at line 42")

    @app.post("/boom/validate")
    async def validate(payload: Payload) -> Payload:
        return payload

    return app


@pytest.fixture
async def error_client(error_app: FastAPI) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False lets us observe the 500 response instead of the exception.
    transport = ASGITransport(app=error_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_not_found_uses_error_envelope(error_client: AsyncClient) -> None:
    response = await error_client.get("/boom/not-found")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Recipe not found."}}


async def test_conflict_maps_to_409(error_client: AsyncClient) -> None:
    response = await error_client.get("/boom/conflict")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_media_validation_status_follows_code(error_client: AsyncClient) -> None:
    response = await error_client.get("/boom/too-large")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_unhandled_exception_returns_generic_500(error_client: AsyncClient) -> None:
    response = await error_client.get("/boom/unexpected")
    assert response.status_code == 500
    body = response.json()
    assert body == {"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}}
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


async def test_validation_error_returns_422_with_field_details(error_client: AsyncClient) -> None:
    response = await error_client.post("/boom/validate", json={"count": "not-a-number"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "body.count"


async def test_unknown_route_uses_error_envelope(error_client: AsyncClient) -> None:
    response = await error_client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_responses_carry_request_id(error_client: AsyncClient) -> None:
    response = await error_client.get("/boom/not-found")
    assert response.headers["X-Request-ID"]

    response = await error_client.get(
        "/boom/not-found", headers={"X-Request-ID": "client-supplied-id-1"}
    )
    assert response.headers["X-Request-ID"] == "client-supplied-id-1"
