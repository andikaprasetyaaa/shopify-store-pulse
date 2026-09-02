from __future__ import annotations

"""
Shopify Store Pulse API.

This module only wires the application together:
it creates the FastAPI instance, registers the
routers and translates domain errors into HTTP
responses. All query logic lives in services/.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT_DIR),
    )

import duckdb
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from analytics.metrics import (
    MetricsError,
)
from api.deps import (
    DashboardDataError,
)
from api.routers import (
    analyst,
    dashboard,
    system,
)


app = FastAPI(
    title="Shopify Store Pulse API",
    version="1.0.0",
    description=(
        "Read-only analytical API "
        "for Shopify Store Pulse."
    ),
)

app.include_router(system.router)
app.include_router(dashboard.router)
app.include_router(analyst.router)


# The Vite build emits hashed files under
# frontend/dist/assets, which index.html references by
# absolute path. Mounting the directory keeps the "/"
# route serving a single HTML file exactly as before.
if system.ASSETS_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(
            directory=system.ASSETS_DIR,
        ),
        name="assets",
    )


# ============================================================
# Error handling
# ============================================================
#
# Every data route used to repeat the same
# try/except returning a 500. Registering the
# handlers once keeps the routers free of error
# plumbing and guarantees one consistent response
# shape.


def error_response(
    exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
        },
    )


@app.exception_handler(
    DashboardDataError
)
def handle_dashboard_error(
    request: Request,
    exc: DashboardDataError,
) -> JSONResponse:
    return error_response(exc)


@app.exception_handler(MetricsError)
def handle_metrics_error(
    request: Request,
    exc: MetricsError,
) -> JSONResponse:
    return error_response(exc)


@app.exception_handler(duckdb.Error)
def handle_duckdb_error(
    request: Request,
    exc: duckdb.Error,
) -> JSONResponse:
    return error_response(exc)
