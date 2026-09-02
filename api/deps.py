from __future__ import annotations

"""
Shared request dependencies for the API.

Holds the database location and the guard every
endpoint runs before touching DuckDB, so routers do
not each re-derive them.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT_DIR),
    )

from storage.database import (
    resolve_read_path,
)


class DashboardDataError(RuntimeError):
    """Raised when the API cannot serve data."""


def database_path() -> Path:
    """
    Resolve the database the API should read.

    Resolved per call rather than cached at import,
    so a serving copy published by the sync after the
    API started is picked up without a restart.
    """

    return resolve_read_path(ROOT_DIR)


def require_database() -> Path:
    """
    Return the readable database path, or raise if
    no database exists yet.
    """

    path = database_path()

    if not path.exists():
        raise DashboardDataError(
            "Production DuckDB does not exist. "
            "Run scripts.sync_data first."
        )

    return path
