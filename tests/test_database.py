from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from storage.database import (
    StorageError,
    StorePulseDatabase,
)


def make_product_catalog(
    *,
    title: str = "Shirt",
) -> dict:
    return {
        "products": [
            {
                "product_id": "product-1",
                "title": title,
                "handle": "shirt",
                "status": "ACTIVE",
                "vendor": "Wooden Ships",
                "product_type": "Apparel",
            }
        ],
        "variants": [
            {
                "variant_id": "variant-1",
                "product_id": "product-1",
                "title": "Small",
                "sku": "SHIRT-S",
                "price": "25.00",
                "inventory_item_id": "inventory-1",
            }
        ],
    }


def make_inventory_catalog(
    *,
    available: int = 10,
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
            }
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
            }
        ],
    }


def make_order_catalog(
    *,
    fulfillment_status: str = "UNFULFILLED",
    current_quantity: int = 2,
) -> dict:
    return {
        "orders": [
            {
                "order_id": "order-1",
                "order_name": "#1001",
                "created_at": "2026-08-31T10:00:00Z",
                "updated_at": "2026-08-31T10:05:00Z",
                "cancelled_at": None,
                "financial_status": "PAID",
                "fulfillment_status": fulfillment_status,
                "total_price": "50.00",
                "currency_code": "USD",
            }
        ],
        "line_items": [
            {
                "line_item_id": "line-1",
                "order_id": "order-1",
                "order_name": "#1001",
                "product_id": "product-1",
                "variant_id": "variant-1",
                "name": "Shirt - Small",
                "title": "Shirt",
                "sku": "SHIRT-S",
                "quantity": 2,
                "current_quantity": current_quantity,
                "original_total": "50.00",
                "current_discounted_total": "45.00",
                "currency_code": "USD",
            }
        ],
    }


def make_analytics() -> dict:
    return {
        "sales_daily": {
            "columns": [
                {
                    "name": "day",
                    "data_type": "DATE",
                    "display_name": "Day",
                },
                {
                    "name": "total_sales",
                    "data_type": "MONEY",
                    "display_name": "Total sales",
                },
            ],
            "rows": [
                {
                    "day": "2026-08-30",
                    "total_sales": "1000.00",
                },
                {
                    "day": "2026-08-31",
                    "total_sales": "1200.00",
                },
            ],
        },
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
                    "day": "2026-08-31",
                    "sessions": 500,
                }
            ],
        },
    }


def query_one(
    database_path: Path,
    sql: str,
):
    connection = duckdb.connect(
        str(database_path),
        read_only=True,
    )

    try:
        return connection.execute(
            sql
        ).fetchone()

    finally:
        connection.close()


def query_all(
    database_path: Path,
    sql: str,
):
    connection = duckdb.connect(
        str(database_path),
        read_only=True,
    )

    try:
        return connection.execute(
            sql
        ).fetchall()

    finally:
        connection.close()


def test_database_schema_is_created(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        counts = database.table_counts()

    assert counts == {
        "products": 0,
        "product_variants": 0,
        "inventory_items": 0,
        "inventory_snapshots": 0,
        "orders": 0,
        "order_line_items": 0,
        "analytics_snapshots": 0,
        "analytics_snapshot_rows": 0,
        "forecast_runs": 0,
    }

    assert database_path.exists()


def test_product_catalog_is_upserted(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    timestamp = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_product_catalog(
            make_product_catalog(
                title="Old Shirt"
            ),
            collected_at=timestamp,
        )

        database.save_product_catalog(
            make_product_catalog(
                title="Updated Shirt"
            ),
            collected_at=timestamp,
        )

        counts = database.table_counts()

    assert counts["products"] == 1
    assert counts["product_variants"] == 1

    result = query_one(
        database_path,
        """
        SELECT title
        FROM products
        WHERE product_id = 'product-1'
        """,
    )

    assert result is not None
    assert result[0] == "Updated Shirt"


def test_inventory_keeps_historical_snapshots(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    first_snapshot = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    second_snapshot = (
        first_snapshot
        + timedelta(hours=1)
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_inventory(
            make_inventory_catalog(
                available=10
            ),
            snapshot_at=first_snapshot,
        )

        database.save_inventory(
            make_inventory_catalog(
                available=7
            ),
            snapshot_at=second_snapshot,
        )

        counts = database.table_counts()

    assert counts[
        "inventory_items"
    ] == 1

    assert counts[
        "inventory_snapshots"
    ] == 2

    rows = query_all(
        database_path,
        """
        SELECT available
        FROM inventory_snapshots
        ORDER BY snapshot_at
        """,
    )

    assert rows == [
        (10,),
        (7,),
    ]


def test_orders_are_upserted(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    first_collection = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    second_collection = (
        first_collection
        + timedelta(minutes=30)
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_orders(
            make_order_catalog(
                fulfillment_status=(
                    "UNFULFILLED"
                ),
                current_quantity=2,
            ),
            collected_at=first_collection,
        )

        database.save_orders(
            make_order_catalog(
                fulfillment_status=(
                    "FULFILLED"
                ),
                current_quantity=1,
            ),
            collected_at=second_collection,
        )

        counts = database.table_counts()

    assert counts["orders"] == 1
    assert counts["order_line_items"] == 1

    order_result = query_one(
        database_path,
        """
        SELECT fulfillment_status
        FROM orders
        WHERE order_id = 'order-1'
        """,
    )

    assert order_result is not None
    assert order_result[0] == "FULFILLED"

    line_result = query_one(
        database_path,
        """
        SELECT current_quantity
        FROM order_line_items
        WHERE line_item_id = 'line-1'
        """,
    )

    assert line_result is not None
    assert line_result[0] == 1


def test_analytics_snapshots_are_saved(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    snapshot_at = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_analytics(
            make_analytics(),
            snapshot_at=snapshot_at,
        )

        counts = database.table_counts()

    assert counts[
        "analytics_snapshots"
    ] == 2

    assert counts[
        "analytics_snapshot_rows"
    ] == 3

    sales_result = query_one(
        database_path,
        """
        SELECT row_count
        FROM analytics_snapshots
        WHERE dataset_name = 'sales_daily'
        """,
    )

    assert sales_result is not None
    assert sales_result[0] == 2

    sessions_result = query_one(
        database_path,
        """
        SELECT row_count
        FROM analytics_snapshots
        WHERE dataset_name = 'sessions_daily'
        """,
    )

    assert sessions_result is not None
    assert sessions_result[0] == 1


def test_timestamp_must_include_timezone(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    naive_timestamp = datetime(
        2026,
        9,
        1,
        8,
        0,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        with pytest.raises(
            StorageError,
            match="timezone",
        ):
            database.save_inventory(
                make_inventory_catalog(),
                snapshot_at=naive_timestamp,
            )

def test_same_snapshot_bucket_overwrites_inventory(
    tmp_path: Path,
) -> None:
    """
    Two hourly syncs landing in the same bucket must
    replace each other instead of duplicating rows.
    """

    database_path = (
        tmp_path / "test.duckdb"
    )

    snapshot_at = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_inventory(
            make_inventory_catalog(
                available=10
            ),
            snapshot_at=snapshot_at,
        )

        database.save_inventory(
            make_inventory_catalog(
                available=4
            ),
            snapshot_at=snapshot_at,
        )

        counts = database.table_counts()

    assert counts[
        "inventory_snapshots"
    ] == 1

    assert query_all(
        database_path,
        """
        SELECT available
        FROM inventory_snapshots
        """,
    ) == [(4,)]


def test_shrinking_catalog_leaves_no_stale_rows(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    snapshot_at = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    catalog = make_inventory_catalog(
        available=10
    )

    extra_level = dict(
        catalog["inventory_levels"][0]
    )

    extra_level[
        "inventory_level_id"
    ] = "level-2"

    catalog["inventory_levels"].append(
        extra_level
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_inventory(
            catalog,
            snapshot_at=snapshot_at,
        )

        # Second run sees only one level.
        database.save_inventory(
            make_inventory_catalog(
                available=10
            ),
            snapshot_at=snapshot_at,
        )

        counts = database.table_counts()

    assert counts[
        "inventory_snapshots"
    ] == 1


def test_same_snapshot_bucket_overwrites_analytics(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    snapshot_at = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_analytics(
            make_analytics(),
            snapshot_at=snapshot_at,
        )

        database.save_analytics(
            make_analytics(),
            snapshot_at=snapshot_at,
        )

        counts = database.table_counts()

    assert counts[
        "analytics_snapshots"
    ] == 2

    assert counts[
        "analytics_snapshot_rows"
    ] == 3


def test_prune_snapshots_removes_old_rows_only(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    old_snapshot = datetime(
        2026,
        7,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    recent_snapshot = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_inventory(
            make_inventory_catalog(
                available=10
            ),
            snapshot_at=old_snapshot,
        )

        database.save_analytics(
            make_analytics(),
            snapshot_at=old_snapshot,
        )

        database.save_inventory(
            make_inventory_catalog(
                available=7
            ),
            snapshot_at=recent_snapshot,
        )

        deleted = database.prune_snapshots(
            before=datetime(
                2026,
                8,
                1,
                tzinfo=timezone.utc,
            ),
        )

        counts = database.table_counts()

    assert deleted[
        "inventory_snapshots"
    ] == 1

    assert deleted[
        "analytics_snapshots"
    ] == 2

    assert counts[
        "inventory_snapshots"
    ] == 1

    assert counts[
        "analytics_snapshot_rows"
    ] == 0

    # Current-state tables are never pruned.
    assert counts[
        "inventory_items"
    ] == 1


def test_latest_order_update_is_incremental_watermark(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    collected_at = datetime(
        2026,
        9,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        assert (
            database.latest_order_update()
            is None
        )

        database.save_orders(
            make_order_catalog(),
            collected_at=collected_at,
        )

        watermark = (
            database.latest_order_update()
        )

    assert watermark is not None


def make_predictions() -> list[dict]:
    return [
        {
            "day": date(2026, 9, 3),
            "predicted": 100.0,
            "lower": 80.0,
            "upper": 120.0,
        },
        {
            "day": date(2026, 9, 4),
            "predicted": 110.0,
            "lower": 85.0,
            "upper": 135.0,
        },
    ]


def test_forecast_run_is_saved_with_horizon(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    forecast_at = datetime(
        2026,
        9,
        2,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_forecast(
            make_predictions(),
            metric="orders",
            model_name="damped_trend",
            forecast_at=forecast_at,
        )

    rows = query_all(
        database_path,
        """
        SELECT horizon, target_day, predicted
        FROM forecast_runs
        ORDER BY horizon
        """,
    )

    assert [row[0] for row in rows] == [1, 2]
    assert rows[0][1] == date(2026, 9, 3)


def test_forecasts_from_different_runs_coexist(
    tmp_path: Path,
) -> None:
    """
    A forecast made a week ago and one made today for
    the same day must both survive, otherwise the
    accuracy of long-horizon predictions can never be
    measured.
    """

    database_path = (
        tmp_path / "test.duckdb"
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        for day in [1, 2]:
            database.save_forecast(
                make_predictions(),
                metric="orders",
                model_name="damped_trend",
                forecast_at=datetime(
                    2026,
                    9,
                    day,
                    8,
                    0,
                    tzinfo=timezone.utc,
                ),
            )

        counts = database.table_counts()

    assert counts["forecast_runs"] == 4


def test_rerunning_one_forecast_overwrites(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    forecast_at = datetime(
        2026,
        9,
        2,
        8,
        0,
        tzinfo=timezone.utc,
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_forecast(
            make_predictions(),
            metric="orders",
            model_name="damped_trend",
            forecast_at=forecast_at,
        )

        revised = make_predictions()
        revised[0]["predicted"] = 999.0

        database.save_forecast(
            revised,
            metric="orders",
            model_name="damped_trend",
            forecast_at=forecast_at,
        )

        counts = database.table_counts()

    assert counts["forecast_runs"] == 2

    assert query_one(
        database_path,
        """
        SELECT predicted
        FROM forecast_runs
        WHERE horizon = 1
        """,
    )[0] == 999.0


def test_empty_forecast_is_ignored(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path / "test.duckdb"
    )

    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_forecast(
            [],
            metric="orders",
            model_name="damped_trend",
        )

        counts = database.table_counts()

    assert counts["forecast_runs"] == 0
