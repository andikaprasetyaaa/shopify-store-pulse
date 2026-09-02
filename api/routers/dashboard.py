from __future__ import annotations

"""
Dashboard routes.

Routers stay thin on purpose: read the query
parameters, hand them to a service, return what it
produces. Errors are turned into HTTP responses
centrally in api.app, so there is no try/except here.
"""

from typing import Any

from fastapi import APIRouter, Query

from services.forecast import build_forecast
from services.funnel import build_funnel
from services.inventory import build_inventory
from services.metadata import database_metadata
from services.overview import build_overview
from services.signals import build_signals

router = APIRouter(
    tags=["dashboard"],
)


@router.get("/api/overview")
def overview(
    days: int = Query(
        default=30,
        ge=1,
        le=60,
    ),
) -> dict[str, Any]:
    return build_overview(days)


@router.get("/api/inventory")
def inventory(
    threshold: int = Query(
        default=5,
        ge=0,
        le=1000000,
    ),
    search: str = Query(
        default="",
        max_length=100,
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
    ),
) -> dict[str, Any]:
    return build_inventory(
        threshold,
        search,
        limit,
    )


@router.get("/api/funnel")
def funnel() -> dict[str, Any]:
    return build_funnel()


@router.get("/api/signals")
def signals() -> dict[str, Any]:
    return build_signals()


@router.get("/api/data-health")
def data_health() -> dict[str, Any]:
    return database_metadata()


@router.get("/api/forecast")
def forecast(
    metric: str = Query(
        default="orders",
        pattern="^(orders|revenue)$",
    ),
    horizon: int = Query(
        default=7,
        ge=1,
        le=14,
    ),
    history_days: int = Query(
        default=30,
        ge=7,
        le=60,
    ),
) -> dict[str, Any]:
    return build_forecast(
        metric,
        horizon,
        history_days,
    )
