from __future__ import annotations

import sys

from pydantic import ValidationError

from collectors.analytics import (
    AnalyticsDataError,
    collect_store_pulse_analytics,
)
from shopify.client import (
    ShopifyClient,
    ShopifyError,
)
from shopify.config import ShopifyConfig


SAMPLE_LIMIT = 7


def main() -> int:
    print(
        "Shopify Store Pulse - Analytics Check"
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
        f"[INFO] Shop: {config.shop_domain}"
    )

    print(
        f"[INFO] API version: "
        f"{config.api_version}"
    )

    print(
        "[INFO] Collecting ShopifyQL analytics..."
    )

    try:
        with ShopifyClient(
            config
        ) as client:
            analytics = (
                collect_store_pulse_analytics(
                    client
                )
            )

    except (
        ShopifyError,
        AnalyticsDataError,
    ) as exc:
        print(
            "[FAIL] Analytics collection failed: "
            f"{exc}",
            file=sys.stderr,
        )

        print(
            "[INFO] Verify read_reports and "
            "Shopify protected customer data "
            "Level 2 access."
        )

        return 1

    sales = analytics[
        "sales_daily"
    ]

    sessions = analytics[
        "sessions_daily"
    ]

    print(
        "[OK] Sales rows collected: "
        f"{len(sales['rows'])}"
    )

    print(
        "[OK] Session rows collected: "
        f"{len(sessions['rows'])}"
    )

    print()
    print("Daily sales sample:")

    for row in sales[
        "rows"
    ][:SAMPLE_LIMIT]:
        print(
            f"  {row}"
        )

    if not sales["rows"]:
        print(
            "  No sales rows returned."
        )

    print()
    print("Daily session sample:")

    for row in sessions[
        "rows"
    ][:SAMPLE_LIMIT]:
        print(
            f"  {row}"
        )

    if not sessions["rows"]:
        print(
            "  No session rows returned."
        )

    print()

    print(
        "[PASS] ShopifyQL analytics "
        "collector smoke test completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )