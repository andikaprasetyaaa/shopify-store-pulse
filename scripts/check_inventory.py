from __future__ import annotations

import sys

from pydantic import ValidationError

from collectors.inventory import (
    InventoryDataError,
    collect_inventory,
)
from shopify.client import (
    ShopifyClient,
    ShopifyError,
)
from shopify.config import ShopifyConfig


SMOKE_TEST_VARIANT_LIMIT = 20
SAMPLE_LIMIT = 5


def main() -> int:
    print(
        "Shopify Store Pulse - Inventory Check"
    )

    try:
        config = ShopifyConfig.from_env()

    except ValidationError as exc:
        print(
            f"[FAIL] Configuration error: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"[INFO] Shop: {config.shop_domain}"
    )

    print(
        f"[INFO] API version: {config.api_version}"
    )

    print(
        "[INFO] Smoke test variant limit: "
        f"{SMOKE_TEST_VARIANT_LIMIT}"
    )

    print(
        "[INFO] Collecting inventory sample..."
    )

    try:
        with ShopifyClient(
            config
        ) as client:
            catalog = collect_inventory(
                client,
                page_size=100,
                max_items=(
                    SMOKE_TEST_VARIANT_LIMIT
                ),
            )

    except (
        ShopifyError,
        InventoryDataError,
    ) as exc:
        print(
            "[FAIL] Inventory collection failed: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    inventory_items = catalog[
        "inventory_items"
    ]

    inventory_levels = catalog[
        "inventory_levels"
    ]

    print(
        "[OK] Inventory items collected: "
        f"{len(inventory_items)}"
    )

    print(
        "[OK] Inventory levels collected: "
        f"{len(inventory_levels)}"
    )

    tracked_count = sum(
        1
        for item in inventory_items
        if item["tracked"]
    )

    print(
        "[OK] Tracked inventory items: "
        f"{tracked_count}"
    )

    locations = {
        (
            level["location_id"],
            level["location_name"],
        )
        for level in inventory_levels
    }

    print(
        "[OK] Locations represented: "
        f"{len(locations)}"
    )

    print()
    print("Inventory samples:")

    for level in inventory_levels[
        :SAMPLE_LIMIT
    ]:
        sku = level["sku"] or "-"

        print(
            "  "
            f"{level['product_title']} | "
            f"SKU={sku} | "
            f"Location={level['location_name']} | "
            f"Available={level['available']}"
        )

    if not inventory_levels:
        print(
            "  No inventory levels returned "
            "for this sample."
        )

    print()

    print(
        "[PASS] Shopify inventory collector "
        "smoke test completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )