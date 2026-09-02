from __future__ import annotations

"""
Routes that do not read store data: the served
frontend and the liveness probe.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.deps import ROOT_DIR, database_path

router = APIRouter()

# The frontend is a TypeScript app built by Vite, so
# what is served is the build output rather than the
# source. `npm run build` in frontend/ produces it, and
# frontend/dist is not committed.
FRONTEND_DIR = (
    ROOT_DIR
    / "frontend"
    / "dist"
)

FRONTEND_PATH = (
    FRONTEND_DIR
    / "index.html"
)

ASSETS_DIR = (
    FRONTEND_DIR
    / "assets"
)


@router.get(
    "/",
    include_in_schema=False,
)
def frontend() -> FileResponse:
    if not FRONTEND_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "frontend/dist/index.html does "
                "not exist. Run 'npm install && "
                "npm run build' in frontend/."
            ),
        )

    return FileResponse(
        FRONTEND_PATH
    )


@router.get(
    "/api/health",
    tags=["system"],
)
def health() -> dict[str, Any]:
    return {
        "status":
            "ok",

        "database_exists":
            database_path().exists(),

        "mode":
            "read-only",

        "shopify_direct_access":
            False,
    }
