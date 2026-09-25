import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app import __version__

pytestmark = pytest.mark.integration


async def test_health_reports_database_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "database": "ok"}


async def test_openapi_is_served_and_health_is_documented(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/health"]["get"]
    assert operation["summary"] == "Service health"
    assert operation["description"]
    assert "200" in operation["responses"]


def test_every_api_operation_has_summary_and_description(app: FastAPI) -> None:
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method, operation in methods.items():
            assert operation.get("summary"), f"{method.upper()} {path} has no summary"
            assert operation.get("description"), f"{method.upper()} {path} has no description"
