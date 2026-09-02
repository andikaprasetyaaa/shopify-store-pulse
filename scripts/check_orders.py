from __future__ import annotations

import sys

from pydantic import ValidationError

from collectors.orders import (
    OrderDataError,
    collect_orders,
)
from shopify.client import (
    ShopifyClient,
    ShopifyError,
)
from shopify.config import ShopifyConfig


SMOKE_TEST_ORDER_LIMIT = 20
SAMPLE_LIMIT = 5


def main() -> int:
    print(
        "Shopify Store Pulse - Orders Check"
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

    print(
        f"[INFO] Shop: "
        f"{config.shop_domain}"
    )

    print(
        f"[INFO] API version: "
        f"{config.api_version}"
    )

    print(
        "[INFO] Smoke test order limit: "
        f"{SMOKE_TEST_ORDER_LIMIT}"
    )

    print(
        "[INFO] Collecting order sample..."
    )

    try:
        with ShopifyClient(
            config
        ) as client:
            catalog = collect_orders(
                client,
                page_size=50,
                max_items=(
                    SMOKE_TEST_ORDER_LIMIT
                ),
            )

    except (
        ShopifyError,
        OrderDataError,
    ) as exc:
        print(
            "[FAIL] Order collection failed: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    orders = catalog[
        "orders"
    ]

    line_items = catalog[
        "line_items"
    ]

    print(
        "[OK] Orders collected: "
        f"{len(orders)}"
    )

    print(
        "[OK] Line items collected: "
        f"{len(line_items)}"
    )

    cancelled_count = sum(
        1
        for order in orders
        if order["cancelled_at"] is not None
    )

    print(
        "[OK] Cancelled orders in sample: "
        f"{cancelled_count}"
    )

    currencies = {
        order["currency_code"]
        for order in orders
    }

    if currencies:
        print(
            "[OK] Currencies represented: "
            + ", ".join(
                sorted(currencies)
            )
        )
    else:
        print(
            "[INFO] No currencies represented"
        )

    print()
    print("Order samples:")

    for order in orders[
        :SAMPLE_LIMIT
    ]:
        financial_status = (
            order["financial_status"]
            or "-"
        )

        print(
            "  "
            f"{order['order_name']} | "
            f"{order['created_at']} | "
            f"{financial_status} | "
            f"{order['fulfillment_status']} | "
            f"{order['total_price']} "
            f"{order['currency_code']}"
        )

    if not orders:
        print(
            "  No orders returned "
            "for this sample."
        )

    print()
    print("Line item samples:")

    for item in line_items[
        :SAMPLE_LIMIT
    ]:
        sku = item["sku"] or "-"

        print(
            "  "
            f"{item['order_name']} | "
            f"{item['title']} | "
            f"SKU={sku} | "
            f"Qty={item['quantity']} | "
            f"CurrentQty="
            f"{item['current_quantity']} | "
            f"Total="
            f"{item['current_discounted_total']} "
            f"{item['currency_code']}"
        )

    if not line_items:
        print(
            "  No line items returned "
            "for this sample."
        )

    print()

    print(
        "[PASS] Shopify order collector "
        "smoke test completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )