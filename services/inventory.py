from __future__ import annotations

"""
Inventory payload: stock summary plus the low-stock
table the dashboard lists.
"""

from typing import Any

import duckdb

from analytics.metrics import (
    StorePulseMetrics,
)
from api.deps import (
    database_path,
    require_database,
)
from api.formatting import (
    iso_value,
)


def build_inventory(
    threshold: int,
    search: str,
    limit: int,
) -> dict[str, Any]:
    require_database()

    with StorePulseMetrics(
        database_path()
    ) as metrics:
        summary = (
            metrics
            .latest_inventory_summary()
        )

    connection = duckdb.connect(
        str(database_path()),
        read_only=True,
    )

    try:
        snapshot_row = (
            connection.execute(
                """
                SELECT
                    MAX(snapshot_at)
                FROM inventory_snapshots
                """
            )
            .fetchone()
        )

        if (
            not snapshot_row
            or snapshot_row[0]
            is None
        ):
            return {
                "summary":
                    {},

                "items":
                    [],

                "threshold":
                    threshold,

                "search":
                    search,
            }

        snapshot_at = (
            snapshot_row[0]
        )

        conditions = [
            "snapshot_at = ?"
        ]

        parameters: list[Any] = [
            snapshot_at
        ]

        cleaned_search = (
            search.strip().lower()
        )

        if cleaned_search:
            conditions.append(
                """
                (
                    LOWER(product_title)
                        LIKE ?
                    OR
                    LOWER(
                        COALESCE(
                            sku,
                            ''
                        )
                    )
                        LIKE ?
                )
                """
            )

            pattern = (
                "%"
                + cleaned_search
                + "%"
            )

            parameters.extend(
                [
                    pattern,
                    pattern,
                ]
            )

        where_sql = (
            " AND ".join(
                conditions
            )
        )

        parameters.append(
            threshold
        )

        parameters.append(
            limit
        )

        rows = (
            connection.execute(
                f"""
                SELECT
                    variant_id,
                    product_id,
                    MAX(
                        product_title
                    ) AS product_title,
                    MAX(
                        sku
                    ) AS sku,
                    SUM(
                        available
                    ) AS available,
                    COUNT(
                        DISTINCT
                        location_id
                    ) AS locations

                FROM inventory_snapshots

                WHERE
                    {where_sql}

                GROUP BY
                    variant_id,
                    product_id

                HAVING
                    SUM(available)
                    <= ?

                ORDER BY
                    available ASC,
                    product_title ASC,
                    -- variant_id is unique after
                    -- the GROUP BY, so it makes
                    -- the ordering total. Without
                    -- it, rows tying on available
                    -- and product_title are cut
                    -- arbitrarily by LIMIT and the
                    -- last row changes between
                    -- requests.
                    variant_id ASC

                LIMIT ?
                """,
                parameters,
            )
            .fetchall()
        )

    finally:
        connection.close()

    items = [
        {
            "variant_id":
                row[0],

            "product_id":
                row[1],

            "product_title":
                row[2],

            "sku":
                row[3],

            "available":
                int(
                    row[4]
                ),

            "locations":
                int(
                    row[5]
                ),
        }
        for row in rows
    ]

    return {
        "summary":
            {
                "snapshot_at":
                    iso_value(
                        summary[
                            "snapshot_at"
                        ]
                    ),

                "inventory_items":
                    summary[
                        "inventory_items"
                    ],

                "inventory_levels":
                    summary[
                        "inventory_levels"
                    ],

                "locations":
                    summary[
                        "locations"
                    ],

                "tracked_items":
                    summary[
                        "tracked_items"
                    ],

                "total_available":
                    summary[
                        "total_available"
                    ],

                "out_of_stock_levels":
                    summary[
                        "out_of_stock_levels"
                    ],
            },

        "threshold":
            threshold,

        "search":
            search,

        "returned":
            len(
                items
            ),

        "items":
            items,
    }
