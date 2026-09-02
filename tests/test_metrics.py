from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from analytics.metrics import (
    MetricsError,
    StorePulseMetrics,
)
from storage.database import StorePulseDatabase


def utc(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
) -> datetime:
    return datetime(
        year,
        month,
        day,
        hour,
        tzinfo=timezone.utc,
    )


def make_orders() -> dict:
    return {
        "orders": [
            {
                "order_id": "order-1",
                "order_name": "#1001",
                "created_at": "2026-08-30T10:00:00Z",
                "updated_at": "2026-08-30T10:05:00Z",
                "cancelled_at": None,
                "financial_status": "PAID",
                "fulfillment_status": "FULFILLED",
                "total_price": "100.00",
                "currency_code": "USD",
            },
            {
                "order_id": "order-2",
                "order_name": "#1002",
                "created_at": "2026-08-31T11:00:00Z",
                "updated_at": "2026-08-31T11:05:00Z",
                "cancelled_at": None,
                "financial_status": "PAID",
                "fulfillment_status": "FULFILLED",
                "total_price": "200.00",
                "currency_code": "USD",
            },
            {
                "order_id": "order-3",
                "order_name": "#1003",
                "created_at": "2026-08-31T12:00:00Z",
                "updated_at": "2026-08-31T12:05:00Z",
                "cancelled_at": "2026-08-31T13:00:00Z",
                "financial_status": "VOIDED",
                "fulfillment_status": "UNFULFILLED",
                "total_price": "500.00",
                "currency_code": "USD",
            },
        ],
        "line_items": [
            {
                "line_item_id": "line-1",
                "order_id": "order-1",
                "order_name": "#1001",
                "product_id": "product-1",
                "variant_id": "variant-1",
                "name": "Shirt",
                "title": "Shirt",
                "sku": "SHIRT-S",
                "quantity": 2,
                "current_quantity": 2,
                "original_total": "100.00",
                "current_discounted_total": "100.00",
                "currency_code": "USD",
            },
            {
                "line_item_id": "line-2",
                "order_id": "order-2",
                "order_name": "#1002",
                "product_id": "product-2",
                "variant_id": "variant-2",
                "name": "Sweater",
                "title": "Sweater",
                "sku": "SWEATER-M",
                "quantity": 3,
                "current_quantity": 3,
                "original_total": "200.00",
                "current_discounted_total": "200.00",
                "currency_code": "USD",
            },
            {
                "line_item_id": "line-3",
                "order_id": "order-3",
                "order_name": "#1003",
                "product_id": "product-3",
                "variant_id": "variant-3",
                "name": "Cancelled Product",
                "title": "Cancelled Product",
                "sku": "CANCELLED",
                "quantity": 10,
                "current_quantity": 10,
                "original_total": "500.00",
                "current_discounted_total": "500.00",
                "currency_code": "USD",
            },
        ],
    }


def make_inventory(
    available: int,
) -> dict:
    return {
        "inventory_items": [
            {
                "inventory_item_id": "inventory-1",
                "variant_id": "variant-1",
                "product_id": "product-1",
                "product_title": "Shirt",
                "sku": "SHIRT-S",
                "tracked": True,
            },
            {
                "inventory_item_id": "inventory-2",
                "variant_id": "variant-2",
                "product_id": "product-2",
                "product_title": "Sweater",
                "sku": "SWEATER-M",
                "tracked": True,
            },
        ],
        "inventory_levels": [
            {
                "inventory_level_id": "level-1",
                "inventory_item_id": "inventory-1",
                "variant_id": "variant-1",
                "product_id": "product-1",
                "product_title": "Shirt",
                "sku": "SHIRT-S",
                "tracked": True,
                "location_id": "location-1",
                "location_name": "Warehouse",
                "available": available,
            },
            {
                "inventory_level_id": "level-2",
                "inventory_item_id": "inventory-2",
                "variant_id": "variant-2",
                "product_id": "product-2",
                "product_title": "Sweater",
                "sku": "SWEATER-M",
                "tracked": True,
                "location_id": "location-1",
                "location_name": "Warehouse",
                "available": 0,
            },
        ],
    }


def make_analytics() -> dict:
    return {
        "sessions_daily": {
            "columns": [
                {
                    "name": "day",
                    "data_type": "DATE",
                    "display_name": "Day",
                },
                {
                    "name": "sessions",
                    "data_type": "INTEGER",
                    "display_name": "Sessions",
                },
            ],
            "rows": [
                {
                    "day": "2026-08-30",
                    "sessions": 1000,
                    "online_store_visitors": 800,
                    "conversion_rate": 0.025,
                    "sessions_with_cart_additions": 200,
                    "sessions_that_reached_checkout": 100,
                    "sessions_that_completed_checkout": 25,
                },
                {
                    "day": "2026-08-31",
                    "sessions": 1200,
                    "online_store_visitors": 950,
                    "conversion_rate": 0.03,
                    "sessions_with_cart_additions": 250,
                    "sessions_that_reached_checkout": 130,
                    "sessions_that_completed_checkout": 36,
                },
            ],
        }
    }


def create_database(
    path: Path,
) -> None:
    with StorePulseDatabase(
        path
    ) as database:
        database.save_orders(
            make_orders(),
            collected_at=utc(
                2026,
                9,
                1,
            ),
        )

        database.save_inventory(
            make_inventory(15),
            snapshot_at=utc(
                2026,
                9,
                1,
                8,
            ),
        )

        database.save_inventory(
            make_inventory(10),
            snapshot_at=utc(
                2026,
                9,
                1,
                9,
            ),
        )

        database.save_analytics(
            make_analytics(),
            snapshot_at=utc(
                2026,
                9,
                1,
                10,
            ),
        )


def test_order_summary(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        result = metrics.order_summary()

    assert result["orders"] == 2

    assert result["revenue"] == Decimal(
        "300.00"
    )

    assert result["aov"] == Decimal(
        "150.00"
    )

    assert result["units_sold"] == 5

    assert result["currency_code"] == "USD"


def test_cancelled_orders_can_be_included(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        result = metrics.order_summary(
            exclude_cancelled=False
        )

    assert result["orders"] == 3

    assert result["revenue"] == Decimal(
        "800.00"
    )

    assert result["units_sold"] == 15


def test_order_date_filter(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        result = metrics.order_summary(
            start_at=utc(
                2026,
                8,
                31,
            ),
            end_at=utc(
                2026,
                9,
                1,
            ),
        )

    assert result["orders"] == 1

    assert result["revenue"] == Decimal(
        "200.00"
    )

    assert result["units_sold"] == 3


def test_daily_order_metrics(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        result = (
            metrics.daily_order_metrics()
        )

    assert len(result) == 2

    assert result[0] == {
        "day": "2026-08-30",
        "revenue": Decimal("100.00"),
        "orders": 1,
        "aov": Decimal("100.00"),
        "units_sold": 2,
        "currency_code": "USD",
    }

    assert result[1] == {
        "day": "2026-08-31",
        "revenue": Decimal("200.00"),
        "orders": 1,
        "aov": Decimal("200.00"),
        "units_sold": 3,
        "currency_code": "USD",
    }


def test_latest_inventory_summary(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        result = (
            metrics.latest_inventory_summary()
        )

    assert result[
        "inventory_items"
    ] == 2

    assert result[
        "inventory_levels"
    ] == 2

    assert result[
        "locations"
    ] == 1

    assert result[
        "tracked_items"
    ] == 2

    # Latest snapshot:
    # Shirt = 10
    # Sweater = 0
    assert result[
        "total_available"
    ] == 10

    assert result[
        "out_of_stock_levels"
    ] == 1


def test_latest_inventory_by_variant(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        result = (
            metrics.latest_inventory_by_variant()
        )

    assert len(result) == 2

    # Sorted by available ASC.
    assert result[0][
        "variant_id"
    ] == "variant-2"

    assert result[0][
        "available"
    ] == 0

    assert result[1][
        "variant_id"
    ] == "variant-1"

    assert result[1][
        "available"
    ] == 10


def test_latest_funnel_metrics(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        result = (
            metrics.latest_funnel_metrics()
        )

    assert result is not None

    assert result["day"] == (
        "2026-08-31"
    )

    assert result["sessions"] == 1200.0

    assert (
        result["online_store_visitors"]
        == 950.0
    )

    assert (
        result["conversion_rate"]
        == 0.03
    )

    assert (
        result[
            "sessions_that_completed_checkout"
        ]
        == 36.0
    )


def test_overview(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        overview = metrics.overview()

    assert overview[
        "orders"
    ][
        "orders"
    ] == 2

    assert overview[
        "inventory"
    ][
        "total_available"
    ] == 10

    assert overview[
        "funnel"
    ] is not None


def test_missing_database_is_rejected(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "missing.duckdb"
    )

    with pytest.raises(
        MetricsError,
        match="does not exist",
    ):
        StorePulseMetrics(
            database_path
        )


def test_naive_datetime_filter_is_rejected(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "metrics.duckdb"
    )

    create_database(
        database_path
    )

    with StorePulseMetrics(
        database_path
    ) as metrics:
        with pytest.raises(
            ValueError,
            match="timezone",
        ):
            metrics.order_summary(
                start_at=datetime(
                    2026,
                    8,
                    1,
                )
            )