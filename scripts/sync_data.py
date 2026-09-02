from __future__ import annotations

import argparse
import gc
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
from pydantic import ValidationError

from collectors.analytics import (
    AnalyticsDataError,
    collect_store_pulse_analytics,
)
from collectors.inventory import (
    InventoryDataError,
    collect_inventory,
)
from collectors.orders import (
    OrderDataError,
    collect_orders,
)
from collectors.products import (
    ProductDataError,
    collect_product_catalog,
)
from shopify.client import (
    ShopifyClient,
    ShopifyError,
)
from shopify.config import ShopifyConfig
from analytics.forecast import (
    ForecastError,
    Point,
    forecast,
)
from storage.database import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_SERVING_PATH,
    StorageError,
    StorePulseDatabase,
    publish_serving_copy,
)


DATABASE_PATH = Path(DEFAULT_DATABASE_PATH)

SERVING_PATH = Path(DEFAULT_SERVING_PATH)

LOCK_PATH = Path(
    str(DATABASE_PATH) + ".sync.lock"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync full Shopify read-only data "
            "into Store Pulse DuckDB."
        )
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete the production DuckDB "
            "before syncing."
        ),
    )

    parser.add_argument(
        "--skip-products",
        action="store_true",
        help=(
            "Skip full product catalog sync."
        ),
    )

    parser.add_argument(
        "--skip-analytics",
        action="store_true",
        help=(
            "Skip ShopifyQL analytics sync."
        ),
    )

    parser.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "Only refetch orders updated since "
            "the newest stored order update. "
            "Existing rows are overwritten by "
            "primary key."
        ),
    )

    parser.add_argument(
        "--overlap-minutes",
        type=int,
        default=90,
        help=(
            "Safety window subtracted from the "
            "incremental watermark so nothing is "
            "lost between runs (default: 90)."
        ),
    )

    parser.add_argument(
        "--snapshot-bucket",
        choices=["hour", "day", "exact"],
        default="day",
        help=(
            "Rounding applied to snapshot "
            "timestamps. Reruns inside the same "
            "bucket overwrite the previous "
            "snapshot, so hourly syncing with a "
            "daily bucket keeps data fresh while "
            "retaining one snapshot per day "
            "(default: day)."
        ),
    )

    parser.add_argument(
        "--skip-forecast",
        action="store_true",
        help=(
            "Skip writing the daily forecast."
        ),
    )

    parser.add_argument(
        "--forecast-horizon",
        type=int,
        default=14,
        help=(
            "Days ahead to forecast and store "
            "(default: 14)."
        ),
    )

    parser.add_argument(
        "--no-publish",
        action="store_true",
        help=(
            "Skip refreshing the read-only serving "
            "copy that the API and dashboard read."
        ),
    )

    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help=(
            "Delete snapshots older than N days "
            "after a successful sync. "
            "0 disables pruning (default: 30)."
        ),
    )

    return parser.parse_args()


FORECAST_MODEL = "damped_trend"


def load_forecast_history(
    database: StorePulseDatabase,
) -> list[Point]:
    """
    Daily order counts up to yesterday.

    Today is excluded because it is still filling up;
    a partial day would look like demand collapsing.
    """

    rows = database.query(
        """
        SELECT
            created_at::DATE AS day,
            COUNT(*) AS value
        FROM orders
        WHERE cancelled_at IS NULL
          AND created_at::DATE < CURRENT_DATE
        GROUP BY 1
        ORDER BY 1
        """
    )

    return [
        Point(
            day=row[0],
            value=float(row[1]),
        )
        for row in rows
    ]


def bucket_timestamp(
    moment: datetime,
    bucket: str,
) -> datetime:
    """
    Round a sync timestamp down so repeated runs
    inside the same window share one snapshot key.
    """

    if bucket == "day":
        return moment.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    if bucket == "hour":
        return moment.replace(
            minute=0,
            second=0,
            microsecond=0,
        )

    return moment


def acquire_lock() -> bool:
    """
    Take a single-writer lock so overlapping
    scheduled runs cannot collide on DuckDB.
    """

    LOCK_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        handle = os.open(
            LOCK_PATH,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY,
        )

    except FileExistsError:
        try:
            owner = int(
                LOCK_PATH.read_text().strip()
            )

        except (ValueError, OSError):
            owner = None

        if owner is not None:
            try:
                os.kill(owner, 0)

            except OSError:
                # Stale lock from a killed run.
                LOCK_PATH.unlink(
                    missing_ok=True
                )

                return acquire_lock()

            return False

        LOCK_PATH.unlink(missing_ok=True)

        return acquire_lock()

    with os.fdopen(handle, "w") as stream:
        stream.write(str(os.getpid()))

    return True


def release_lock() -> None:
    LOCK_PATH.unlink(missing_ok=True)


def reset_database() -> None:
    paths = [
        DATABASE_PATH,
        Path(str(DATABASE_PATH) + ".wal"),
        SERVING_PATH,
        Path(str(SERVING_PATH) + ".wal"),
    ]

    for path in paths:
        if path.exists():
            path.unlink()


def main() -> int:
    args = parse_args()

    print(
        "Shopify Store Pulse - "
        "Production Data Sync"
    )

    try:
        config = ShopifyConfig.from_env()

    except ValidationError as exc:
        print(
            "[FAIL] Configuration error: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    if not acquire_lock():
        print(
            "[SKIP] Another sync is already "
            "running. Nothing to do.",
        )
        return 0

    try:
        return run_sync(args, config)

    finally:
        release_lock()


def run_sync(
    args: argparse.Namespace,
    config: ShopifyConfig,
) -> int:
    if args.reset:
        print(
            "[INFO] Resetting production database..."
        )
        reset_database()

    sync_at = datetime.now(
        timezone.utc
    )

    snapshot_at = bucket_timestamp(
        sync_at,
        args.snapshot_bucket,
    )

    print(
        f"[INFO] Shop: {config.shop_domain}"
    )

    print(
        f"[INFO] API version: "
        f"{config.api_version}"
    )

    print(
        f"[INFO] Database: {DATABASE_PATH}"
    )

    print(
        "[INFO] Sync timestamp: "
        f"{sync_at.isoformat()}"
    )

    print(
        "[INFO] Snapshot bucket "
        f"({args.snapshot_bucket}): "
        f"{snapshot_at.isoformat()}"
    )

    try:
        with ShopifyClient(
            config
        ) as client:
            with StorePulseDatabase(
                DATABASE_PATH
            ) as database:

                # ====================================
                # Products
                # ====================================

                if not args.skip_products:
                    print()
                    print(
                        "[INFO] Syncing full "
                        "product catalog..."
                    )

                    products = (
                        collect_product_catalog(
                            client,
                            page_size=250,
                            max_items=None,
                        )
                    )

                    product_count = len(
                        products["products"]
                    )

                    variant_count = len(
                        products["variants"]
                    )

                    print(
                        "[OK] Products collected: "
                        f"{product_count}"
                    )

                    print(
                        "[OK] Variants collected: "
                        f"{variant_count}"
                    )

                    database.save_product_catalog(
                        products,
                        collected_at=sync_at,
                    )

                    print(
                        "[OK] Product catalog saved"
                    )

                    del products
                    gc.collect()

                else:
                    print()
                    print(
                        "[INFO] Product sync skipped"
                    )

                # ====================================
                # Inventory
                # ====================================

                print()
                print(
                    "[INFO] Syncing full inventory..."
                )

                inventory = collect_inventory(
                    client,
                    page_size=100,
                    max_items=None,
                )

                inventory_item_count = len(
                    inventory["inventory_items"]
                )

                inventory_level_count = len(
                    inventory["inventory_levels"]
                )

                print(
                    "[OK] Inventory items: "
                    f"{inventory_item_count}"
                )

                print(
                    "[OK] Inventory levels: "
                    f"{inventory_level_count}"
                )

                database.save_inventory(
                    inventory,
                    snapshot_at=snapshot_at,
                )

                print(
                    "[OK] Inventory snapshot saved"
                )

                del inventory
                gc.collect()

                # ====================================
                # Orders
                # ====================================

                print()

                order_filter = None

                if args.incremental:
                    watermark = (
                        database
                        .latest_order_update()
                    )

                    if watermark is not None:
                        since = (
                            watermark
                            - timedelta(
                                minutes=(
                                    args
                                    .overlap_minutes
                                )
                            )
                        )

                        order_filter = (
                            "updated_at:>="
                            + since
                            .astimezone(
                                timezone.utc
                            )
                            .strftime(
                                "%Y-%m-%dT"
                                "%H:%M:%SZ"
                            )
                        )

                if order_filter is None:
                    print(
                        "[INFO] Syncing all "
                        "accessible orders..."
                    )

                else:
                    print(
                        "[INFO] Syncing orders "
                        f"matching {order_filter}"
                    )

                orders = collect_orders(
                    client,
                    page_size=100,
                    max_items=None,
                    query_filter=order_filter,
                )

                order_count = len(
                    orders["orders"]
                )

                line_item_count = len(
                    orders["line_items"]
                )

                print(
                    "[OK] Orders collected: "
                    f"{order_count}"
                )

                print(
                    "[OK] Line items collected: "
                    f"{line_item_count}"
                )

                database.save_orders(
                    orders,
                    collected_at=sync_at,
                )

                print(
                    "[OK] Orders saved"
                )

                del orders
                gc.collect()

                # ====================================
                # ShopifyQL
                # ====================================

                if not args.skip_analytics:
                    print()
                    print(
                        "[INFO] Syncing "
                        "ShopifyQL analytics..."
                    )

                    try:
                        analytics = (
                            collect_store_pulse_analytics(
                                client
                            )
                        )

                        sales_row_count = len(
                            analytics[
                                "sales_daily"
                            ][
                                "rows"
                            ]
                        )

                        session_row_count = len(
                            analytics[
                                "sessions_daily"
                            ][
                                "rows"
                            ]
                        )

                        print(
                            "[OK] Sales analytics rows: "
                            f"{sales_row_count}"
                        )

                        print(
                            "[OK] Session analytics rows: "
                            f"{session_row_count}"
                        )

                        database.save_analytics(
                            analytics,
                            snapshot_at=snapshot_at,
                        )

                        print(
                            "[OK] ShopifyQL "
                            "analytics saved"
                        )

                    except (
                        ShopifyError,
                        AnalyticsDataError,
                    ) as exc:
                        print(
                            "[WARN] ShopifyQL "
                            "analytics skipped: "
                            f"{exc}"
                        )

                else:
                    print()
                    print(
                        "[INFO] Analytics "
                        "sync skipped"
                    )

                # ====================================
                # Forecast
                # ====================================
                #
                # Written after the data lands so the
                # forecast always reflects the sync
                # that just finished. Each run is
                # stored under its own timestamp, so
                # today's prediction for next Tuesday
                # sits beside the one made a week ago
                # and both can be scored once the
                # actual arrives.

                if not args.skip_forecast:
                    print()

                    try:
                        history = (
                            load_forecast_history(
                                database
                            )
                        )

                        predictions = forecast(
                            history,
                            horizon=(
                                args
                                .forecast_horizon
                            ),
                            model_name=(
                                FORECAST_MODEL
                            ),
                        )

                        database.save_forecast(
                            [
                                {
                                    "day":
                                        item.day,

                                    "predicted":
                                        item.predicted,

                                    "lower":
                                        item.lower,

                                    "upper":
                                        item.upper,
                                }
                                for item in predictions
                            ],
                            metric="orders",
                            model_name=(
                                FORECAST_MODEL
                            ),
                            forecast_at=sync_at,
                        )

                        print(
                            "[OK] Forecast stored: "
                            f"{len(predictions)} days "
                            f"from {predictions[0].day}"
                        )

                    except (
                        ForecastError,
                        duckdb.Error,
                    ) as exc:
                        print(
                            "[WARN] Forecast "
                            f"skipped: {exc}"
                        )

                else:
                    print()
                    print(
                        "[INFO] Forecast skipped"
                    )

                # ====================================
                # Retention
                # ====================================

                if args.retention_days > 0:
                    cutoff = sync_at - timedelta(
                        days=args.retention_days
                    )

                    deleted = (
                        database.prune_snapshots(
                            before=cutoff,
                        )
                    )

                    total_deleted = sum(
                        deleted.values()
                    )

                    print()
                    print(
                        "[OK] Pruned snapshots "
                        "older than "
                        f"{cutoff.date()}: "
                        f"{total_deleted} rows"
                    )

                database.checkpoint()

                counts = (
                    database.table_counts()
                )

    except (
        ShopifyError,
        ProductDataError,
        InventoryDataError,
        OrderDataError,
        StorageError,
    ) as exc:
        print(
            "[FAIL] Production sync failed: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    # The write connection is closed here, so the
    # database file on disk is complete and can be
    # copied for readers.

    if not args.no_publish:
        try:
            published = publish_serving_copy(
                DATABASE_PATH,
                SERVING_PATH,
            )

            print()
            print(
                "[OK] Serving copy published: "
                f"{published}"
            )

        except StorageError as exc:
            print(
                "[WARN] Serving copy not "
                f"refreshed: {exc}",
                file=sys.stderr,
            )

    print()
    print(
        "Production database row counts:"
    )

    for table, count in (
        counts.items()
    ):
        print(
            f"  {table}: {count}"
        )

    print()

    print(
        "[PASS] Production data "
        "sync completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )