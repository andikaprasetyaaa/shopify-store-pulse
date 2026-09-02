from __future__ import annotations

import sys

from pydantic import ValidationError

from collectors.products import (
    ProductDataError,
    collect_product_catalog,
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
        "Shopify Store Pulse - Product Check"
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
        "[INFO] Smoke test variant limit: "
        f"{SMOKE_TEST_VARIANT_LIMIT}"
    )

    print(
        "[INFO] Collecting product sample..."
    )

    try:
        with ShopifyClient(
            config
        ) as client:
            catalog = (
                collect_product_catalog(
                    client,
                    page_size=100,
                    max_items=(
                        SMOKE_TEST_VARIANT_LIMIT
                    ),
                )
            )

    except (
        ShopifyError,
        ProductDataError,
    ) as exc:
        print(
            "[FAIL] Product collection "
            f"failed: {exc}",
            file=sys.stderr,
        )

        return 1

    products = catalog[
        "products"
    ]

    variants = catalog[
        "variants"
    ]

    print(
        "[OK] Products represented "
        f"in sample: {len(products)}"
    )

    print(
        "[OK] Variants collected: "
        f"{len(variants)}"
    )

    if not variants:
        print(
            "[INFO] No product variants "
            "were returned by Shopify."
        )

        print(
            "[PASS] Product collector "
            "completed with empty catalog"
        )

        return 0

    print()
    print("Product samples:")

    for product in products[
        :SAMPLE_LIMIT
    ]:
        print(
            "  "
            f"{product['product_id']} | "
            f"{product['title']} | "
            f"{product['status']}"
        )

    print()
    print("Variant samples:")

    for variant in variants[
        :SAMPLE_LIMIT
    ]:
        sku = (
            variant["sku"]
            or "-"
        )

        print(
            "  "
            f"{variant['variant_id']} | "
            f"{variant['title']} | "
            f"SKU={sku} | "
            f"Price={variant['price']}"
        )

    print()

    print(
        "[PASS] Shopify product "
        "collector smoke test completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )