from __future__ import annotations

import sys
from decimal import Decimal

from analytics.metrics import (
    MetricsError,
    StorePulseMetrics,
)


LOW_STOCK_SAMPLE_LIMIT = 10


def money(
    value: Decimal,
    currency_code: str | None,
) -> str:
    currency = (
        currency_code
        or "-"
    )

    return (
        f"{value:.2f} "
        f"{currency}"
    )


def main() -> int:
    print(
        "Shopify Store Pulse - Metrics Check"
    )

    try:
        with StorePulseMetrics() as metrics:
            overview = metrics.overview()

            daily = (
                metrics.daily_order_metrics()
            )

            low_stock = (
                metrics.latest_inventory_by_variant(
                    limit=(
                        LOW_STOCK_SAMPLE_LIMIT
                    )
                )
            )

    except MetricsError as exc:
        print(
            "[FAIL] Metrics check failed: "
            f"{exc}",
            file=sys.stderr,
        )

        print(
            "[INFO] Run "
            "python3 -m scripts.check_database "
            "first."
        )

        return 1

    order_metrics = overview[
        "orders"
    ]

    inventory_metrics = overview[
        "inventory"
    ]

    funnel = overview[
        "funnel"
    ]

    print()
    print("Order metrics:")

    print(
        "  Revenue: "
        + money(
            order_metrics[
                "revenue"
            ],
            order_metrics[
                "currency_code"
            ],
        )
    )

    print(
        "  Orders: "
        f"{order_metrics['orders']}"
    )

    print(
        "  AOV: "
        + money(
            order_metrics[
                "aov"
            ],
            order_metrics[
                "currency_code"
            ],
        )
    )

    print(
        "  Units sold: "
        f"{order_metrics['units_sold']}"
    )

    print()
    print("Inventory metrics:")

    print(
        "  Snapshot: "
        f"{inventory_metrics['snapshot_at']}"
    )

    print(
        "  Inventory items: "
        f"{inventory_metrics['inventory_items']}"
    )

    print(
        "  Inventory levels: "
        f"{inventory_metrics['inventory_levels']}"
    )

    print(
        "  Locations: "
        f"{inventory_metrics['locations']}"
    )

    print(
        "  Total available: "
        f"{inventory_metrics['total_available']}"
    )

    print(
        "  Out-of-stock levels: "
        f"{inventory_metrics['out_of_stock_levels']}"
    )

    print()
    print("Funnel metrics:")

    if funnel is None:
        print(
            "  No ShopifyQL funnel "
            "snapshot available."
        )

    else:
        print(
            f"  Day: {funnel['day']}"
        )

        print(
            f"  Sessions: "
            f"{funnel['sessions']}"
        )

        print(
            "  Visitors: "
            f"{funnel['online_store_visitors']}"
        )

        print(
            "  Conversion rate: "
            f"{funnel['conversion_rate']}"
        )

        print(
            "  Cart additions: "
            f"{funnel['sessions_with_cart_additions']}"
        )

        print(
            "  Checkout reached: "
            f"{funnel['sessions_that_reached_checkout']}"
        )

        print(
            "  Checkout completed: "
            f"{funnel['sessions_that_completed_checkout']}"
        )

    print()
    print("Daily order metrics:")

    for row in daily[-7:]:
        print(
            "  "
            f"{row['day']} | "
            f"Revenue="
            f"{row['revenue']} | "
            f"Orders="
            f"{row['orders']} | "
            f"AOV="
            f"{row['aov']} | "
            f"Units="
            f"{row['units_sold']}"
        )

    if not daily:
        print(
            "  No daily order data."
        )

    print()
    print("Lowest inventory variants:")

    for row in low_stock:
        sku = (
            row["sku"]
            or "-"
        )

        print(
            "  "
            f"{row['product_title']} | "
            f"SKU={sku} | "
            f"Available="
            f"{row['available']} | "
            f"Locations="
            f"{row['locations']}"
        )

    if not low_stock:
        print(
            "  No inventory data."
        )

    print()

    print(
        "[PASS] Metrics smoke test completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )