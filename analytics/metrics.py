from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict

import duckdb

from storage.database import DEFAULT_DATABASE_PATH


ZERO_MONEY = Decimal("0.00")


class MetricsError(RuntimeError):
    """Raised when KPI calculation cannot be performed safely."""


class OrderMetrics(TypedDict):
    revenue: Decimal
    orders: int
    aov: Decimal
    units_sold: int
    currency_code: str | None


class DailyOrderMetrics(TypedDict):
    day: str
    revenue: Decimal
    orders: int
    aov: Decimal
    units_sold: int
    currency_code: str | None


class InventoryMetrics(TypedDict):
    snapshot_at: datetime | None
    inventory_items: int
    inventory_levels: int
    locations: int
    tracked_items: int
    total_available: int
    out_of_stock_levels: int


class VariantInventoryMetric(TypedDict):
    variant_id: str
    product_id: str
    product_title: str
    sku: str | None
    available: int
    locations: int


class FunnelMetrics(TypedDict):
    snapshot_at: datetime
    day: str | None
    sessions: float | None
    online_store_visitors: float | None
    conversion_rate: float | None
    sessions_with_cart_additions: float | None
    sessions_that_reached_checkout: float | None
    sessions_that_completed_checkout: float | None


class StoreOverview(TypedDict):
    orders: OrderMetrics
    inventory: InventoryMetrics
    funnel: FunnelMetrics | None


class StorePulseMetrics:
    """
    Read-only KPI layer for Shopify Store Pulse.

    Reads normalized data from DuckDB.

    This class does not:
    - Call Shopify
    - Write to DuckDB
    - Build baselines
    - Detect anomalies
    - Render dashboards
    """

    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
    ) -> None:
        self.database_path = Path(
            database_path
        )

        if not self.database_path.exists():
            raise MetricsError(
                "DuckDB database does not exist: "
                f"{self.database_path}"
            )

        self._connection = duckdb.connect(
            str(self.database_path),
            read_only=True,
        )

    def __enter__(
        self,
    ) -> "StorePulseMetrics":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def overview(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> StoreOverview:
        """
        Return the first Store Pulse overview.

        Includes:
        - Revenue
        - Orders
        - AOV
        - Units sold
        - Current inventory
        - Current funnel metrics if ShopifyQL exists
        """

        return {
            "orders": self.order_summary(
                start_at=start_at,
                end_at=end_at,
            ),
            "inventory":
                self.latest_inventory_summary(),
            "funnel":
                self.latest_funnel_metrics(),
        }

    def order_summary(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        exclude_cancelled: bool = True,
    ) -> OrderMetrics:
        """
        Calculate order KPIs.

        Revenue currently means:
        sum of stored order.total_price values.

        By default cancelled orders are excluded.

        Refunds are not separately netted because
        refund data is not collected in the current MVP.
        """

        where_sql, parameters = (
            _build_order_filter(
                start_at=start_at,
                end_at=end_at,
                exclude_cancelled=exclude_cancelled,
            )
        )

        currency_code = (
            self._single_currency(
                where_sql,
                parameters,
            )
        )

        row = self._connection.execute(
            f"""
            SELECT
                COUNT(*) AS orders,
                COALESCE(
                    SUM(total_price),
                    DECIMAL '0.00'
                ) AS revenue
            FROM orders
            {where_sql}
            """,
            parameters,
        ).fetchone()

        if row is None:
            raise MetricsError(
                "Could not calculate order metrics."
            )

        order_count = int(
            row[0]
        )

        revenue = _to_decimal(
            row[1]
        )

        if order_count > 0:
            aov = revenue / Decimal(
                order_count
            )
        else:
            aov = ZERO_MONEY

        units_row = self._connection.execute(
            f"""
            SELECT
                COALESCE(
                    SUM(li.current_quantity),
                    0
                )
            FROM order_line_items AS li
            INNER JOIN orders AS o
                ON o.order_id = li.order_id
            {where_sql.replace(
                "created_at",
                "o.created_at",
            ).replace(
                "cancelled_at",
                "o.cancelled_at",
            )}
            """,
            parameters,
        ).fetchone()

        if units_row is None:
            raise MetricsError(
                "Could not calculate units sold."
            )

        units_sold = int(
            units_row[0]
        )

        return {
            "revenue": revenue,
            "orders": order_count,
            "aov": aov,
            "units_sold": units_sold,
            "currency_code": currency_code,
        }

    def daily_order_metrics(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        exclude_cancelled: bool = True,
    ) -> list[DailyOrderMetrics]:
        """
        Return daily Revenue, Orders, AOV,
        and Units Sold.

        This will later become input for:
        - baseline.py
        - anomalies.py
        """

        where_sql, parameters = (
            _build_order_filter(
                start_at=start_at,
                end_at=end_at,
                exclude_cancelled=exclude_cancelled,
            )
        )

        currency_code = (
            self._single_currency(
                where_sql,
                parameters,
            )
        )

        rows = self._connection.execute(
            f"""
            WITH filtered_orders AS (
                SELECT
                    order_id,
                    created_at,
                    total_price
                FROM orders
                {where_sql}
            ),

            units_by_order AS (
                SELECT
                    order_id,
                    SUM(current_quantity)
                        AS units_sold
                FROM order_line_items
                GROUP BY order_id
            )

            SELECT
                CAST(
                    f.created_at AS DATE
                ) AS day,

                COUNT(*) AS orders,

                COALESCE(
                    SUM(f.total_price),
                    DECIMAL '0.00'
                ) AS revenue,

                COALESCE(
                    SUM(u.units_sold),
                    0
                ) AS units_sold

            FROM filtered_orders AS f

            LEFT JOIN units_by_order AS u
                ON u.order_id = f.order_id

            GROUP BY
                CAST(
                    f.created_at AS DATE
                )

            ORDER BY day ASC
            """,
            parameters,
        ).fetchall()

        result: list[
            DailyOrderMetrics
        ] = []

        for row in rows:
            day = str(
                row[0]
            )

            order_count = int(
                row[1]
            )

            revenue = _to_decimal(
                row[2]
            )

            units_sold = int(
                row[3]
            )

            if order_count > 0:
                aov = (
                    revenue
                    / Decimal(order_count)
                )
            else:
                aov = ZERO_MONEY

            result.append(
                {
                    "day": day,
                    "revenue": revenue,
                    "orders": order_count,
                    "aov": aov,
                    "units_sold":
                        units_sold,
                    "currency_code":
                        currency_code,
                }
            )

        return result

    def latest_inventory_summary(
        self,
    ) -> InventoryMetrics:
        """
        Calculate store inventory metrics from
        the latest inventory snapshot.

        Inventory Level:
            sum of available quantity across
            all inventory levels in that snapshot.
        """

        snapshot_row = (
            self._connection.execute(
                """
                SELECT MAX(snapshot_at)
                FROM inventory_snapshots
                """
            ).fetchone()
        )

        if (
            snapshot_row is None
            or snapshot_row[0] is None
        ):
            return {
                "snapshot_at": None,
                "inventory_items": 0,
                "inventory_levels": 0,
                "locations": 0,
                "tracked_items": 0,
                "total_available": 0,
                "out_of_stock_levels": 0,
            }

        snapshot_at = snapshot_row[0]

        row = self._connection.execute(
            """
            SELECT
                COUNT(
                    DISTINCT inventory_item_id
                ) AS inventory_items,

                COUNT(*) AS inventory_levels,

                COUNT(
                    DISTINCT location_id
                ) AS locations,

                COUNT(
                    DISTINCT CASE
                        WHEN tracked
                        THEN inventory_item_id
                    END
                ) AS tracked_items,

                COALESCE(
                    SUM(available),
                    0
                ) AS total_available,

                COALESCE(
                    SUM(
                        CASE
                            WHEN available <= 0
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS out_of_stock_levels

            FROM inventory_snapshots

            WHERE snapshot_at = ?
            """,
            [
                snapshot_at
            ],
        ).fetchone()

        if row is None:
            raise MetricsError(
                "Could not calculate "
                "inventory metrics."
            )

        return {
            "snapshot_at":
                snapshot_at,

            "inventory_items":
                int(row[0]),

            "inventory_levels":
                int(row[1]),

            "locations":
                int(row[2]),

            "tracked_items":
                int(row[3]),

            "total_available":
                int(row[4]),

            "out_of_stock_levels":
                int(row[5]),
        }

    def latest_inventory_by_variant(
        self,
        *,
        limit: int | None = None,
    ) -> list[VariantInventoryMetric]:
        """
        Return current available inventory summed
        across locations for each variant.
        """

        if (
            limit is not None
            and limit < 1
        ):
            raise ValueError(
                "limit must be at least 1 "
                "or None."
            )

        snapshot_row = (
            self._connection.execute(
                """
                SELECT MAX(snapshot_at)
                FROM inventory_snapshots
                """
            ).fetchone()
        )

        if (
            snapshot_row is None
            or snapshot_row[0] is None
        ):
            return []

        snapshot_at = snapshot_row[0]

        sql = """
            SELECT
                variant_id,
                product_id,
                MAX(product_title)
                    AS product_title,
                MAX(sku)
                    AS sku,
                SUM(available)
                    AS available,
                COUNT(
                    DISTINCT location_id
                ) AS locations

            FROM inventory_snapshots

            WHERE snapshot_at = ?

            GROUP BY
                variant_id,
                product_id

            ORDER BY
                available ASC,
                product_title ASC
        """

        parameters: list[Any] = [
            snapshot_at
        ]

        if limit is not None:
            sql += "\nLIMIT ?"
            parameters.append(
                limit
            )

        rows = self._connection.execute(
            sql,
            parameters,
        ).fetchall()

        result: list[
            VariantInventoryMetric
        ] = []

        for row in rows:
            result.append(
                {
                    "variant_id":
                        str(row[0]),

                    "product_id":
                        str(row[1]),

                    "product_title":
                        str(row[2]),

                    "sku":
                        (
                            str(row[3])
                            if row[3]
                            is not None
                            else None
                        ),

                    "available":
                        int(row[4]),

                    "locations":
                        int(row[5]),
                }
            )

        return result

    def latest_funnel_metrics(
        self,
    ) -> FunnelMetrics | None:
        """
        Return the latest daily ShopifyQL
        sessions/funnel row.

        Returns None when ShopifyQL analytics
        have not been stored yet.
        """

        snapshot_row = (
            self._connection.execute(
                """
                SELECT MAX(snapshot_at)
                FROM analytics_snapshots
                WHERE dataset_name =
                    'sessions_daily'
                """
            ).fetchone()
        )

        if (
            snapshot_row is None
            or snapshot_row[0] is None
        ):
            return None

        snapshot_at = snapshot_row[0]

        rows = self._connection.execute(
            """
            SELECT
                row_index,
                CAST(row_json AS VARCHAR)

            FROM analytics_snapshot_rows

            WHERE
                dataset_name =
                    'sessions_daily'
                AND snapshot_at = ?

            ORDER BY row_index ASC
            """,
            [
                snapshot_at
            ],
        ).fetchall()

        if not rows:
            return None

        decoded_rows: list[
            dict[str, Any]
        ] = []

        for _, row_json in rows:
            decoded_rows.append(
                _decode_json_object(
                    row_json
                )
            )

        latest_row = max(
            decoded_rows,
            key=lambda row: str(
                row.get(
                    "day",
                    "",
                )
            ),
        )

        return {
            "snapshot_at":
                snapshot_at,

            "day":
                _optional_text(
                    latest_row.get(
                        "day"
                    )
                ),

            "sessions":
                _optional_number(
                    latest_row.get(
                        "sessions"
                    )
                ),

            "online_store_visitors":
                _optional_number(
                    latest_row.get(
                        "online_store_visitors"
                    )
                ),

            "conversion_rate":
                _optional_number(
                    latest_row.get(
                        "conversion_rate"
                    )
                ),

            "sessions_with_cart_additions":
                _optional_number(
                    latest_row.get(
                        "sessions_with_cart_additions"
                    )
                ),

            "sessions_that_reached_checkout":
                _optional_number(
                    latest_row.get(
                        "sessions_that_reached_checkout"
                    )
                ),

            "sessions_that_completed_checkout":
                _optional_number(
                    latest_row.get(
                        "sessions_that_completed_checkout"
                    )
                ),
        }

    def _single_currency(
        self,
        where_sql: str,
        parameters: list[Any],
    ) -> str | None:
        """
        Never silently sum multiple currencies.

        We currently use Shopify shopMoney, so normally
        only one currency should exist.
        """

        rows = self._connection.execute(
            f"""
            SELECT DISTINCT currency_code
            FROM orders
            {where_sql}
            ORDER BY currency_code
            """,
            parameters,
        ).fetchall()

        currencies = [
            str(row[0])
            for row in rows
            if row[0] is not None
        ]

        if not currencies:
            return None

        if len(currencies) > 1:
            raise MetricsError(
                "Multiple currencies detected: "
                + ", ".join(currencies)
                + ". Revenue cannot be safely "
                "aggregated into one value."
            )

        return currencies[0]


def _build_order_filter(
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    exclude_cancelled: bool,
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    parameters: list[Any] = []

    if exclude_cancelled:
        conditions.append(
            "cancelled_at IS NULL"
        )

    if start_at is not None:
        conditions.append(
            "created_at >= ?"
        )

        parameters.append(
            _normalize_datetime(
                start_at
            )
        )

    if end_at is not None:
        conditions.append(
            "created_at < ?"
        )

        parameters.append(
            _normalize_datetime(
                end_at
            )
        )

    if (
        start_at is not None
        and end_at is not None
        and _normalize_datetime(start_at)
        >= _normalize_datetime(end_at)
    ):
        raise ValueError(
            "start_at must be earlier "
            "than end_at."
        )

    if not conditions:
        return "", parameters

    return (
        "WHERE "
        + " AND ".join(
            conditions
        ),
        parameters,
    )


def _normalize_datetime(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        raise ValueError(
            "Metric date filters must "
            "include timezone information."
        )

    return value.astimezone(
        timezone.utc
    )


def _to_decimal(
    value: Any,
) -> Decimal:
    if value is None:
        return ZERO_MONEY

    if isinstance(
        value,
        Decimal,
    ):
        return value

    try:
        return Decimal(
            str(value)
        )

    except Exception as exc:
        raise MetricsError(
            f"Invalid decimal metric: {value}"
        ) from exc


def _decode_json_object(
    value: Any,
) -> dict[str, Any]:
    if isinstance(
        value,
        dict,
    ):
        return value

    if not isinstance(
        value,
        str,
    ):
        raise MetricsError(
            "Analytics row JSON "
            "is invalid."
        )

    try:
        decoded = json.loads(
            value
        )

    except json.JSONDecodeError as exc:
        raise MetricsError(
            "Analytics row contains "
            "invalid JSON."
        ) from exc

    if not isinstance(
        decoded,
        dict,
    ):
        raise MetricsError(
            "Analytics row JSON must "
            "contain an object."
        )

    return decoded


def _optional_number(
    value: Any,
) -> float | None:
    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        raise MetricsError(
            "Boolean value cannot "
            "be used as a metric."
        )

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise MetricsError(
            f"Invalid numeric metric: {value}"
        ) from exc


def _optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        return str(value)

    return value