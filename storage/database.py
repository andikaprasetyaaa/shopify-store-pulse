from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


DEFAULT_DATABASE_PATH = Path(
    "data/shopify_store_pulse.duckdb"
)

DEFAULT_SERVING_PATH = Path(
    "data/serving.duckdb"
)


class StorageError(RuntimeError):
    """Raised when local DuckDB storage fails."""


def publish_serving_copy(
    source: str | Path = DEFAULT_DATABASE_PATH,
    target: str | Path = DEFAULT_SERVING_PATH,
) -> Path:
    """
    Publish a read-only serving copy of the database.

    DuckDB allows either one writer or several
    readers, never both. The hourly sync therefore
    holds the write lock on the source database for
    the whole run, which would lock the API and the
    dashboard out for minutes at a time.

    Copying to a temporary file and renaming it into
    place is atomic on the same filesystem, so
    readers either see the previous copy or the new
    one and never a half-written file. Readers that
    already hold the old file keep it open safely
    until they close.

    Call this only after the writing connection has
    been checkpointed and closed, so no
    write-ahead log is left outside the file.
    """

    source_path = Path(source)
    target_path = Path(target)

    if not source_path.exists():
        raise StorageError(
            "Cannot publish serving copy. "
            f"Source '{source_path}' does not exist."
        )

    target_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging_path = target_path.with_name(
        target_path.name + ".tmp"
    )

    try:
        shutil.copy2(
            source_path,
            staging_path,
        )

        os.replace(
            staging_path,
            target_path,
        )

    except OSError as exc:
        staging_path.unlink(
            missing_ok=True
        )

        raise StorageError(
            "Failed to publish serving copy to "
            f"'{target_path}'."
        ) from exc

    return target_path


def resolve_read_path(
    root: str | Path = Path("."),
) -> Path:
    """
    Return the database path readers should use.

    Prefers the serving copy published by the sync
    and falls back to the live database when no copy
    exists yet, so a fresh checkout still works
    before the first sync has run.
    """

    root_path = Path(root)

    serving_path = (
        root_path / DEFAULT_SERVING_PATH
    )

    if serving_path.exists():
        return serving_path

    return root_path / DEFAULT_DATABASE_PATH


class StorePulseDatabase:
    """
    Local analytical storage for Shopify Store Pulse.

    Responsibilities:
    - Create DuckDB schema
    - Store normalized collector outputs
    - Keep inventory snapshots over time
    - Keep ShopifyQL snapshots over time

    This module does not:
    - Call Shopify
    - Calculate KPIs
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

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._connection = duckdb.connect(
            str(self.database_path)
        )

        self.initialize_schema()

    def __enter__(
        self,
    ) -> "StorePulseDatabase":
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

    def initialize_schema(self) -> None:
        """
        Create all raw/local storage tables.

        Safe to run repeatedly.
        """

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                product_id VARCHAR PRIMARY KEY,
                title VARCHAR NOT NULL,
                handle VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                vendor VARCHAR,
                product_type VARCHAR,
                collected_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS product_variants (
                variant_id VARCHAR PRIMARY KEY,
                product_id VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                sku VARCHAR,
                price DECIMAL(18, 2) NOT NULL,
                inventory_item_id VARCHAR NOT NULL,
                collected_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_items (
                inventory_item_id VARCHAR PRIMARY KEY,
                variant_id VARCHAR NOT NULL,
                product_id VARCHAR NOT NULL,
                product_title VARCHAR NOT NULL,
                sku VARCHAR,
                tracked BOOLEAN NOT NULL,
                collected_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_snapshots (
                snapshot_at TIMESTAMPTZ NOT NULL,
                inventory_level_id VARCHAR NOT NULL,
                inventory_item_id VARCHAR NOT NULL,
                variant_id VARCHAR NOT NULL,
                product_id VARCHAR NOT NULL,
                product_title VARCHAR NOT NULL,
                sku VARCHAR,
                tracked BOOLEAN NOT NULL,
                location_id VARCHAR NOT NULL,
                location_name VARCHAR NOT NULL,
                available BIGINT NOT NULL,

                PRIMARY KEY (
                    snapshot_at,
                    inventory_level_id
                )
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR PRIMARY KEY,
                order_name VARCHAR NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                cancelled_at TIMESTAMPTZ,
                financial_status VARCHAR,
                fulfillment_status VARCHAR NOT NULL,
                total_price DECIMAL(18, 2) NOT NULL,
                currency_code VARCHAR NOT NULL,
                collected_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS order_line_items (
                line_item_id VARCHAR PRIMARY KEY,
                order_id VARCHAR NOT NULL,
                order_name VARCHAR NOT NULL,
                product_id VARCHAR,
                variant_id VARCHAR,
                name VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                sku VARCHAR,
                quantity BIGINT NOT NULL,
                current_quantity BIGINT NOT NULL,
                original_total DECIMAL(18, 2) NOT NULL,
                current_discounted_total DECIMAL(18, 2) NOT NULL,
                currency_code VARCHAR NOT NULL,
                collected_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_runs (
                forecast_at TIMESTAMPTZ NOT NULL,
                target_day DATE NOT NULL,
                metric VARCHAR NOT NULL,
                model_name VARCHAR NOT NULL,
                horizon BIGINT NOT NULL,
                predicted DECIMAL(18, 2) NOT NULL,
                lower_bound DECIMAL(18, 2) NOT NULL,
                upper_bound DECIMAL(18, 2) NOT NULL,

                PRIMARY KEY (
                    forecast_at,
                    target_day,
                    metric,
                    model_name
                )
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_snapshots (
                dataset_name VARCHAR NOT NULL,
                snapshot_at TIMESTAMPTZ NOT NULL,
                columns_json JSON NOT NULL,
                row_count BIGINT NOT NULL,

                PRIMARY KEY (
                    dataset_name,
                    snapshot_at
                )
            )
            """
        )

        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_snapshot_rows (
                dataset_name VARCHAR NOT NULL,
                snapshot_at TIMESTAMPTZ NOT NULL,
                row_index BIGINT NOT NULL,
                row_json JSON NOT NULL,

                PRIMARY KEY (
                    dataset_name,
                    snapshot_at,
                    row_index
                )
            )
            """
        )

    def save_product_catalog(
        self,
        catalog: dict[str, Any],
        *,
        collected_at: datetime | None = None,
    ) -> None:
        """
        Store current product and variant state.

        Existing IDs are replaced with the latest
        normalized collector values.
        """

        timestamp = _normalize_timestamp(
            collected_at
        )

        products = _require_list(
            catalog,
            "products",
        )

        variants = _require_list(
            catalog,
            "variants",
        )

        product_rows = [
            {
                **row,
                "collected_at": timestamp,
            }
            for row in products
        ]

        variant_rows = [
            {
                **row,
                "collected_at": timestamp,
            }
            for row in variants
        ]

        try:
            self._connection.execute(
                "BEGIN TRANSACTION"
            )

            self._bulk_upsert(
                table_name="products",
                rows=product_rows,
                columns=[
                    "product_id",
                    "title",
                    "handle",
                    "status",
                    "vendor",
                    "product_type",
                    "collected_at",
                ],
                temporary_view=(
                    "_product_batch"
                ),
            )

            self._bulk_upsert(
                table_name="product_variants",
                rows=variant_rows,
                columns=[
                    "variant_id",
                    "product_id",
                    "title",
                    "sku",
                    "price",
                    "inventory_item_id",
                    "collected_at",
                ],
                temporary_view=(
                    "_variant_batch"
                ),
            )

            self._connection.execute(
                "COMMIT"
            )

        except Exception as exc:
            self._rollback_safely()

            raise StorageError(
                "Failed to save product catalog."
            ) from exc

    def save_inventory(
        self,
        catalog: dict[str, Any],
        *,
        snapshot_at: datetime | None = None,
    ) -> None:
        """
        Store current inventory-item metadata and
        append inventory levels as a historical snapshot.

        Inventory snapshots are intentionally not
        overwritten across different timestamps.

        Rows already stored for the same
        snapshot_at are deleted first, so a repeated
        sync inside one snapshot bucket overwrites
        instead of leaving stale duplicates behind.
        """

        timestamp = _normalize_timestamp(
            snapshot_at
        )

        inventory_items = _require_list(
            catalog,
            "inventory_items",
        )

        inventory_levels = _require_list(
            catalog,
            "inventory_levels",
        )

        item_rows = [
            {
                **row,
                "collected_at": timestamp,
            }
            for row in inventory_items
        ]

        snapshot_rows = [
            {
                "snapshot_at": timestamp,
                **row,
            }
            for row in inventory_levels
        ]

        try:
            self._connection.execute(
                "BEGIN TRANSACTION"
            )

            self._connection.execute(
                """
                DELETE FROM inventory_snapshots
                WHERE snapshot_at = ?
                """,
                [timestamp],
            )

            self._bulk_upsert(
                table_name="inventory_items",
                rows=item_rows,
                columns=[
                    "inventory_item_id",
                    "variant_id",
                    "product_id",
                    "product_title",
                    "sku",
                    "tracked",
                    "collected_at",
                ],
                temporary_view=(
                    "_inventory_item_batch"
                ),
            )

            self._bulk_upsert(
                table_name="inventory_snapshots",
                rows=snapshot_rows,
                columns=[
                    "snapshot_at",
                    "inventory_level_id",
                    "inventory_item_id",
                    "variant_id",
                    "product_id",
                    "product_title",
                    "sku",
                    "tracked",
                    "location_id",
                    "location_name",
                    "available",
                ],
                temporary_view=(
                    "_inventory_snapshot_batch"
                ),
            )

            self._connection.execute(
                "COMMIT"
            )

        except Exception as exc:
            self._rollback_safely()

            raise StorageError(
                "Failed to save inventory."
            ) from exc

    def save_orders(
        self,
        catalog: dict[str, Any],
        *,
        collected_at: datetime | None = None,
    ) -> None:
        """
        Store current order and line-item state.

        Existing Shopify IDs are updated with the
        latest normalized values.

        This is important because order status,
        fulfillment state, refunds, and
        currentQuantity can change over time.
        """

        timestamp = _normalize_timestamp(
            collected_at
        )

        orders = _require_list(
            catalog,
            "orders",
        )

        line_items = _require_list(
            catalog,
            "line_items",
        )

        order_rows = [
            {
                **row,
                "collected_at": timestamp,
            }
            for row in orders
        ]

        line_item_rows = [
            {
                **row,
                "collected_at": timestamp,
            }
            for row in line_items
        ]

        try:
            self._connection.execute(
                "BEGIN TRANSACTION"
            )

            self._bulk_upsert(
                table_name="orders",
                rows=order_rows,
                columns=[
                    "order_id",
                    "order_name",
                    "created_at",
                    "updated_at",
                    "cancelled_at",
                    "financial_status",
                    "fulfillment_status",
                    "total_price",
                    "currency_code",
                    "collected_at",
                ],
                temporary_view=(
                    "_order_batch"
                ),
            )

            self._bulk_upsert(
                table_name="order_line_items",
                rows=line_item_rows,
                columns=[
                    "line_item_id",
                    "order_id",
                    "order_name",
                    "product_id",
                    "variant_id",
                    "name",
                    "title",
                    "sku",
                    "quantity",
                    "current_quantity",
                    "original_total",
                    "current_discounted_total",
                    "currency_code",
                    "collected_at",
                ],
                temporary_view=(
                    "_line_item_batch"
                ),
            )

            self._connection.execute(
                "COMMIT"
            )

        except Exception as exc:
            self._rollback_safely()

            raise StorageError(
                "Failed to save orders."
            ) from exc

    def save_analytics(
        self,
        analytics: dict[str, Any],
        *,
        snapshot_at: datetime | None = None,
    ) -> None:
        """
        Store raw ShopifyQL result snapshots.

        Expected structure:

        {
            "sales_daily": {
                "columns": [...],
                "rows": [...]
            },
            "sessions_daily": {
                "columns": [...],
                "rows": [...]
            }
        }

        The rows remain JSON here intentionally.
        Conversion to daily KPI tables belongs to
        analytics/metrics.py later.
        """

        timestamp = _normalize_timestamp(
            snapshot_at
        )

        snapshot_headers: list[
            dict[str, Any]
        ] = []

        snapshot_rows: list[
            dict[str, Any]
        ] = []

        for dataset_name, dataset in (
            analytics.items()
        ):
            if not isinstance(
                dataset_name,
                str,
            ):
                raise StorageError(
                    "Analytics dataset name "
                    "must be a string."
                )

            if not isinstance(
                dataset,
                dict,
            ):
                raise StorageError(
                    f"Analytics dataset "
                    f"'{dataset_name}' is invalid."
                )

            columns = dataset.get(
                "columns"
            )

            rows = dataset.get(
                "rows"
            )

            if not isinstance(
                columns,
                list,
            ):
                raise StorageError(
                    f"Analytics dataset "
                    f"'{dataset_name}' has "
                    "invalid columns."
                )

            if not isinstance(
                rows,
                list,
            ):
                raise StorageError(
                    f"Analytics dataset "
                    f"'{dataset_name}' has "
                    "invalid rows."
                )

            snapshot_headers.append(
                {
                    "dataset_name":
                        dataset_name,

                    "snapshot_at":
                        timestamp,

                    "columns_json":
                        json.dumps(
                            columns,
                            default=str,
                        ),

                    "row_count":
                        len(rows),
                }
            )

            for row_index, row in enumerate(
                rows
            ):
                if not isinstance(
                    row,
                    dict,
                ):
                    raise StorageError(
                        f"Analytics dataset "
                        f"'{dataset_name}' "
                        "contains an invalid row."
                    )

                snapshot_rows.append(
                    {
                        "dataset_name":
                            dataset_name,

                        "snapshot_at":
                            timestamp,

                        "row_index":
                            row_index,

                        "row_json":
                            json.dumps(
                                row,
                                default=str,
                            ),
                    }
                )

        dataset_names = sorted(
            {
                str(header["dataset_name"])
                for header in snapshot_headers
            }
        )

        try:
            self._connection.execute(
                "BEGIN TRANSACTION"
            )

            for dataset_name in dataset_names:
                for table_name in (
                    "analytics_snapshots",
                    "analytics_snapshot_rows",
                ):
                    self._connection.execute(
                        f"""
                        DELETE FROM {table_name}
                        WHERE dataset_name = ?
                          AND snapshot_at = ?
                        """,
                        [
                            dataset_name,
                            timestamp,
                        ],
                    )

            self._bulk_upsert(
                table_name="analytics_snapshots",
                rows=snapshot_headers,
                columns=[
                    "dataset_name",
                    "snapshot_at",
                    "columns_json",
                    "row_count",
                ],
                temporary_view=(
                    "_analytics_header_batch"
                ),
            )

            self._bulk_upsert(
                table_name=(
                    "analytics_snapshot_rows"
                ),
                rows=snapshot_rows,
                columns=[
                    "dataset_name",
                    "snapshot_at",
                    "row_index",
                    "row_json",
                ],
                temporary_view=(
                    "_analytics_row_batch"
                ),
            )

            self._connection.execute(
                "COMMIT"
            )

        except Exception as exc:
            self._rollback_safely()

            raise StorageError(
                "Failed to save analytics."
            ) from exc

    def save_forecast(
        self,
        predictions: list[dict[str, Any]],
        *,
        metric: str,
        model_name: str,
        forecast_at: datetime | None = None,
    ) -> None:
        """
        Store a forecast run.

        Rows are keyed by when the forecast was made
        as well as the day it targets, so predictions
        are never overwritten by later ones. That is
        what makes honest scoring possible later: the
        forecast for next Tuesday made a week ago
        stays next to the one made yesterday, and
        both can be compared against the actual once
        it arrives.
        """

        if not predictions:
            return

        timestamp = _normalize_timestamp(
            forecast_at
        )

        rows = [
            {
                "forecast_at": timestamp,
                "target_day": row["day"],
                "metric": metric,
                "model_name": model_name,
                "horizon": index,
                "predicted": row["predicted"],
                "lower_bound": row["lower"],
                "upper_bound": row["upper"],
            }
            for index, row in enumerate(
                predictions,
                start=1,
            )
        ]

        try:
            self._connection.execute(
                "BEGIN TRANSACTION"
            )

            self._bulk_upsert(
                table_name="forecast_runs",
                rows=rows,
                columns=[
                    "forecast_at",
                    "target_day",
                    "metric",
                    "model_name",
                    "horizon",
                    "predicted",
                    "lower_bound",
                    "upper_bound",
                ],
                temporary_view=(
                    "_forecast_batch"
                ),
            )

            self._connection.execute(
                "COMMIT"
            )

        except Exception as exc:
            self._rollback_safely()

            raise StorageError(
                "Failed to save forecast."
            ) from exc

    def prune_snapshots(
        self,
        *,
        before: datetime,
    ) -> dict[str, int]:
        """
        Delete snapshot rows older than `before`.

        Only the append-only snapshot tables are
        pruned. Current-state tables (products,
        variants, inventory items, orders, line
        items) are kept in full because they are
        overwritten by primary key instead of
        growing over time.
        """

        cutoff = _normalize_timestamp(
            before
        )

        deleted: dict[str, int] = {}

        tables = [
            "inventory_snapshots",
            "analytics_snapshot_rows",
            "analytics_snapshots",
        ]

        try:
            self._connection.execute(
                "BEGIN TRANSACTION"
            )

            for table_name in tables:
                before_count = (
                    self._connection.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {table_name}
                        WHERE snapshot_at < ?
                        """,
                        [cutoff],
                    ).fetchone()
                )

                self._connection.execute(
                    f"""
                    DELETE FROM {table_name}
                    WHERE snapshot_at < ?
                    """,
                    [cutoff],
                )

                deleted[
                    table_name
                ] = int(
                    before_count[0]
                    if before_count
                    else 0
                )

            self._connection.execute(
                "COMMIT"
            )

        except Exception as exc:
            self._rollback_safely()

            raise StorageError(
                "Failed to prune snapshots."
            ) from exc

        return deleted

    def checkpoint(self) -> None:
        """
        Flush the write-ahead log so the database
        file on disk stays compact between runs.
        """

        try:
            self._connection.execute(
                "CHECKPOINT"
            )

        except Exception as exc:
            raise StorageError(
                "Failed to checkpoint database."
            ) from exc

    def latest_order_update(
        self,
    ) -> datetime | None:
        """
        Return the newest order `updated_at` stored
        locally, used as the incremental sync
        watermark. Returns None on an empty table.
        """

        result = self._connection.execute(
            """
            SELECT MAX(updated_at)
            FROM orders
            """
        ).fetchone()

        if result is None or result[0] is None:
            return None

        return result[0]

    def query(
        self,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> list[tuple]:
        """
        Run a read query on the open write
        connection.

        The sync already holds the single writer
        lock, so it cannot open a second read-only
        connection to the same file. This lets it
        read back what it just wrote.
        """

        try:
            return self._connection.execute(
                sql,
                parameters or [],
            ).fetchall()

        except Exception as exc:
            raise StorageError(
                "Query failed."
            ) from exc

    def table_counts(
        self,
    ) -> dict[str, int]:
        """
        Return row counts for storage diagnostics.
        """

        tables = [
            "products",
            "product_variants",
            "inventory_items",
            "inventory_snapshots",
            "orders",
            "order_line_items",
            "analytics_snapshots",
            "analytics_snapshot_rows",
            "forecast_runs",
        ]

        counts: dict[
            str,
            int
        ] = {}

        for table_name in tables:
            result = self._connection.execute(
                f"""
                SELECT COUNT(*)
                FROM {table_name}
                """
            ).fetchone()

            if result is None:
                raise StorageError(
                    f"Could not count "
                    f"table '{table_name}'."
                )

            counts[
                table_name
            ] = int(result[0])

        return counts

    def _bulk_upsert(
        self,
        *,
        table_name: str,
        rows: list[dict[str, Any]],
        columns: list[str],
        temporary_view: str,
    ) -> None:
        """
        Bulk insert/update using a Pandas DataFrame.

        Primary keys defined in DuckDB determine
        which rows are replaced.
        """

        if not rows:
            return

        frame = pd.DataFrame(
            rows
        )

        missing_columns = [
            column
            for column in columns
            if column not in frame.columns
        ]

        if missing_columns:
            raise StorageError(
                f"Cannot write table "
                f"'{table_name}'. Missing columns: "
                + ", ".join(
                    missing_columns
                )
            )

        frame = frame[
            columns
        ]

        self._connection.register(
            temporary_view,
            frame,
        )

        try:
            column_sql = ", ".join(
                columns
            )

            self._connection.execute(
                f"""
                INSERT OR REPLACE
                INTO {table_name}
                ({column_sql})
                SELECT
                    {column_sql}
                FROM {temporary_view}
                """
            )

        finally:
            self._connection.unregister(
                temporary_view
            )

    def _rollback_safely(
        self,
    ) -> None:
        try:
            self._connection.execute(
                "ROLLBACK"
            )
        except Exception:
            pass


def _normalize_timestamp(
    value: datetime | None,
) -> datetime:
    """
    Ensure timestamps written to DuckDB are UTC
    timezone-aware datetimes.
    """

    if value is None:
        return datetime.now(
            timezone.utc
        )

    if value.tzinfo is None:
        raise StorageError(
            "Storage timestamps must "
            "include timezone information."
        )

    return value.astimezone(
        timezone.utc
    )


def _require_list(
    source: dict[str, Any],
    field: str,
) -> list[dict[str, Any]]:
    value = source.get(
        field
    )

    if not isinstance(
        value,
        list,
    ):
        raise StorageError(
            f"Expected '{field}' "
            "to be a list."
        )

    for row in value:
        if not isinstance(
            row,
            dict,
        ):
            raise StorageError(
                f"'{field}' contains "
                "a non-object row."
            )

    return value