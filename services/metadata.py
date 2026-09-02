from __future__ import annotations

"""
Database metadata and freshness, shared by the API
data-health endpoint and the dashboard footer.
"""

from typing import Any

import duckdb

from api.deps import (
    database_path,
    require_database,
)
from api.formatting import (
    iso_value,
)


def collect_metadata() -> dict[str, Any]:
    require_database()

    connection = duckdb.connect(
        str(database_path()),
        read_only=True,
    )

    try:
        tables = [
            "products",
            "product_variants",
            "inventory_items",
            "inventory_snapshots",
            "orders",
            "order_line_items",
            "analytics_snapshots",
            "analytics_snapshot_rows",
        ]

        counts: dict[
            str,
            int
        ] = {}

        for table in tables:
            result = (
                connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {table}
                    """
                )
                .fetchone()
            )

            counts[
                table
            ] = (
                int(
                    result[0]
                )
                if result
                else 0
            )

        order_info = (
            connection.execute(
                """
                SELECT
                    MIN(
                        CAST(
                            created_at
                            AS DATE
                        )
                    ),
                    MAX(
                        CAST(
                            created_at
                            AS DATE
                        )
                    ),
                    MAX(
                        collected_at
                    )
                FROM orders
                """
            )
            .fetchone()
        )

        inventory_sync = (
            connection.execute(
                """
                SELECT
                    MAX(snapshot_at)
                FROM inventory_snapshots
                """
            )
            .fetchone()
        )

        analytics_sync = (
            connection.execute(
                """
                SELECT
                    MAX(snapshot_at)
                FROM analytics_snapshots
                """
            )
            .fetchone()
        )

        latest_inventory = (
            connection.execute(
                """
                SELECT
                    COUNT(
                        DISTINCT
                        inventory_item_id
                    )
                FROM inventory_snapshots
                WHERE snapshot_at = (
                    SELECT
                        MAX(snapshot_at)
                    FROM inventory_snapshots
                )
                """
            )
            .fetchone()
        )

        return {
            "counts":
                counts,

            "order_start":
                (
                    order_info[0]
                    if order_info
                    else None
                ),

            "order_end":
                (
                    order_info[1]
                    if order_info
                    else None
                ),

            "orders_synced_at":
                (
                    order_info[2]
                    if order_info
                    else None
                ),

            "inventory_synced_at":
                (
                    inventory_sync[0]
                    if (
                        inventory_sync
                        and
                        inventory_sync[0]
                    )
                    else None
                ),

            "analytics_synced_at":
                (
                    analytics_sync[0]
                    if (
                        analytics_sync
                        and
                        analytics_sync[0]
                    )
                    else None
                ),

            "latest_inventory_items":
                (
                    int(
                        latest_inventory[0]
                    )
                    if (
                        latest_inventory
                        and
                        latest_inventory[0]
                    )
                    else 0
                ),
        }

    finally:
        connection.close()


# The dashboard renders native date and datetime
# objects directly, while the API must emit JSON.
# Keeping the query in collect_metadata() and the
# serialisation here means both read exactly the
# same numbers.

TIMESTAMP_KEYS = (
    "order_start",
    "order_end",
    "orders_synced_at",
    "inventory_synced_at",
    "analytics_synced_at",
)


def database_metadata() -> dict[str, Any]:
    """
    JSON-ready metadata for the API.
    """

    raw = collect_metadata()

    payload: dict[str, Any] = {
        "database":
            str(database_path()),
    }

    for key, value in raw.items():
        payload[key] = (
            iso_value(value)
            if key in TIMESTAMP_KEYS
            else value
        )

    return payload
