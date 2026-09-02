from __future__ import annotations

from pathlib import Path

import pytest

from api import deps
from storage.database import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_SERVING_PATH,
)


def test_database_path_prefers_serving_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "ROOT_DIR",
        tmp_path,
    )

    live = tmp_path / DEFAULT_DATABASE_PATH
    serving = tmp_path / DEFAULT_SERVING_PATH

    live.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    live.write_text("")

    assert deps.database_path() == live

    serving.write_text("")

    # Resolved per call, so the copy is picked up
    # without restarting the API.
    assert deps.database_path() == serving


def test_require_database_raises_when_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "ROOT_DIR",
        tmp_path,
    )

    with pytest.raises(
        deps.DashboardDataError
    ):
        deps.require_database()


def test_require_database_returns_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "ROOT_DIR",
        tmp_path,
    )

    live = tmp_path / DEFAULT_DATABASE_PATH

    live.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    live.write_text("")

    assert deps.require_database() == live
