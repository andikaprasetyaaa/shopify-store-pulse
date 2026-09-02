from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from analytics.metrics import MetricsError
from api.app import app
from api.deps import DashboardDataError
from api.routers import dashboard


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    "error",
    [
        DashboardDataError(
            "no database"
        ),
        MetricsError(
            "bad metrics"
        ),
        duckdb.Error(
            "locked"
        ),
    ],
)
def test_domain_errors_become_500(
    client: TestClient,
    monkeypatch,
    error: Exception,
) -> None:
    """
    The per-route try/except was replaced by app-wide
    handlers. Each domain error must still produce
    the same 500 with the message in `detail`.
    """

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(
        dashboard,
        "build_overview",
        fail,
    )

    response = client.get(
        "/api/overview"
    )

    assert response.status_code == 500

    assert response.json() == {
        "detail": str(error),
    }


def test_invalid_query_param_is_422(
    client: TestClient,
) -> None:
    """
    Query validation stays on the router, so out of
    range values must still be rejected before any
    service runs.
    """

    assert client.get(
        "/api/overview",
        params={"days": 0},
    ).status_code == 422

    assert client.get(
        "/api/overview",
        params={"days": 61},
    ).status_code == 422

    assert client.get(
        "/api/inventory",
        params={"limit": 0},
    ).status_code == 422

    assert client.get(
        "/api/inventory",
        params={"threshold": -1},
    ).status_code == 422


def test_health_never_requires_a_database(
    client: TestClient,
) -> None:
    """
    Health is a liveness probe: it must answer even
    when the database is missing.
    """

    response = client.get(
        "/api/health"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == (
        "read-only"
    )


def test_unknown_route_is_404(
    client: TestClient,
) -> None:
    assert client.get(
        "/api/does-not-exist"
    ).status_code == 404
