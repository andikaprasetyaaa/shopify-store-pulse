from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

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
from storage.database import (
    StorageError,
    StorePulseDatabase,
)


PRODUCT_VARIANT_LIMIT = 50
INVENTORY_VARIANT_LIMIT = 20
ORDER_LIMIT = 20

SMOKE_DATABASE_PATH = Path(
    "data/shopify_store_pulse_smoke.duckdb"
)


def reset_smoke_database() -> None:
    paths = [
        SMOKE_DATABASE_PATH,
        Path(
            str(SMOKE_DATABASE_PATH)
            + ".wal"
        ),
    ]

    for path in paths:
        if path.exists():
            path.unlink()


def main() -> int:
    print(
        "Shopify Store Pulse - "
        "Database Smoke Check"
    )

    try:
        config = (
            ShopifyConfig.from_env()
        )

    except ValidationError as exc:
        print(
            "[FAIL] Configuration error: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    reset_smoke_database()

    collected_at = (
        datetime.now(
            timezone.utc
        )
    )

    print(
        f"[INFO] Shop: "
        f"{config.shop_domain}"
    )

    print(
        "[INFO] Smoke database: "
        f"{SMOKE_DATABASE_PATH}"
    )

    try:
        with ShopifyClient(
            config
        ) as client:

            products = (
                collect_product_catalog(
                    client,
                    page_size=100,
                    max_items=(
                        PRODUCT_VARIANT_LIMIT
                    ),
                )
            )

            print(
                "[OK] Products: "
                f"{len(products['products'])} "
                "products, "
                f"{len(products['variants'])} "
                "variants"
            )

            inventory = (
                collect_inventory(
                    client,
                    page_size=100,
                    max_items=(
                        INVENTORY_VARIANT_LIMIT
                    ),
                )
            )

            print(
                "[OK] Inventory: "
                f"{len(inventory['inventory_items'])} "
                "items, "
                f"{len(inventory['inventory_levels'])} "
                "levels"
            )

            orders = collect_orders(
                client,
                page_size=50,
                max_items=ORDER_LIMIT,
            )

            print(
                "[OK] Orders: "
                f"{len(orders['orders'])} "
                "orders, "
                f"{len(orders['line_items'])} "
                "line items"
            )

            analytics = None

            try:
                analytics = (
                    collect_store_pulse_analytics(
                        client
                    )
                )

                print(
                    "[OK] ShopifyQL "
                    "analytics collected"
                )

            except (
                ShopifyError,
                AnalyticsDataError,
            ) as exc:

                print(
                    "[INFO] ShopifyQL skipped: "
                    f"{exc}"
                )

    except (
        ShopifyError,
        ProductDataError,
        InventoryDataError,
        OrderDataError,
    ) as exc:

        print(
            "[FAIL] Shopify collection "
            f"failed: {exc}",
            file=sys.stderr,
        )

        return 1

    try:
        with StorePulseDatabase(
            SMOKE_DATABASE_PATH
        ) as database:

            database.save_product_catalog(
                products,
                collected_at=collected_at,
            )

            database.save_inventory(
                inventory,
                snapshot_at=collected_at,
            )

            database.save_orders(
                orders,
                collected_at=collected_at,
            )

            if analytics is not None:
                database.save_analytics(
                    analytics,
                    snapshot_at=(
                        collected_at
                    ),
                )

            counts = (
                database.table_counts()
            )

    except StorageError as exc:
        print(
            "[FAIL] Smoke database failed: "
            f"{exc}",
            file=sys.stderr,
        )

        return 1

    print()
    print(
        "Smoke database row counts:"
    )

    for table, count in (
        counts.items()
    ):
        print(
            f"  {table}: {count}"
        )

    print()

    print(
        "[PASS] DuckDB smoke "
        "database check completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )