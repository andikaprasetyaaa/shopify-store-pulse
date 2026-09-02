from __future__ import annotations

from datetime import date, datetime

import pytest

from services.metadata import (
    TIMESTAMP_KEYS,
    collect_metadata,
    database_metadata,
)


@pytest.fixture(scope="module")
def raw() -> dict:
    return collect_metadata()


@pytest.fixture(scope="module")
def serialized() -> dict:
    return database_metadata()


def test_core_returns_native_types(
    raw: dict,
) -> None:
    """
    The dashboard renders these directly, so they
    must stay as date/datetime rather than strings.
    """

    if raw["order_start"] is not None:
        assert isinstance(
            raw["order_start"],
            date,
        )

    if raw["orders_synced_at"] is not None:
        assert isinstance(
            raw["orders_synced_at"],
            datetime,
        )


def test_api_serializes_every_timestamp(
    serialized: dict,
) -> None:
    for key in TIMESTAMP_KEYS:
        value = serialized[key]

        if value is not None:
            assert isinstance(value, str)


def test_api_adds_database_path(
    serialized: dict,
    raw: dict,
) -> None:
    assert "database" in serialized
    assert "database" not in raw


def test_both_views_report_the_same_numbers(
    raw: dict,
    serialized: dict,
) -> None:
    """
    The dashboard used to keep its own copy of this
    query, which had already drifted. Sharing one
    core means the two can no longer disagree.
    """

    assert raw["counts"] == serialized["counts"]

    assert (
        raw["latest_inventory_items"]
        == serialized["latest_inventory_items"]
    )


def test_serialization_is_lossless(
    raw: dict,
    serialized: dict,
) -> None:
    for key in TIMESTAMP_KEYS:
        if raw[key] is None:
            assert serialized[key] is None

        else:
            assert serialized[key] == (
                raw[key].isoformat()
            )
