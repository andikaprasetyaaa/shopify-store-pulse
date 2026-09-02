from __future__ import annotations

import sys

from pydantic import ValidationError

from shopify.client import (
    ShopifyClient,
    ShopifyError,
)
from shopify.config import ShopifyConfig
from shopify.queries import (
    GET_ACCESS_SCOPES,
    GET_SHOP,
)


REQUIRED_READ_SCOPES = {
    "read_inventory",
    "read_locations",
    "read_orders",
    "read_products",
    "read_reports",
}


def main() -> int:
    print(
        "Shopify Store Pulse - Connection Check"
    )

    try:
        config = ShopifyConfig.from_env()

    except ValidationError as exc:
        fields = sorted(
            {
                ".".join(
                    str(part)
                    for part in error["loc"]
                )
                for error in exc.errors()
            }
        )

        print(
            "[FAIL] Invalid or missing configuration: "
            + ", ".join(fields),
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

    try:
        with ShopifyClient(
            config
        ) as client:

            shop_data = client.query(
                GET_SHOP
            )

            shop_name = (
                shop_data[
                    "shop"
                ][
                    "name"
                ]
            )

            print(
                "[OK] Authentication successful"
            )

            print(
                "[OK] Connected to Shopify shop: "
                f"{shop_name}"
            )

            scope_data = client.query(
                GET_ACCESS_SCOPES
            )

            scope_items = (
                scope_data[
                    "currentAppInstallation"
                ][
                    "accessScopes"
                ]
            )

            granted_scopes = {
                item["handle"]
                for item in scope_items
                if (
                    isinstance(
                        item,
                        dict,
                    )
                    and isinstance(
                        item.get("handle"),
                        str,
                    )
                )
            }

    except (
        ShopifyError,
        KeyError,
        TypeError,
    ) as exc:

        print(
            "[FAIL] Shopify connection "
            f"check failed: {exc}",
            file=sys.stderr,
        )

        return 1

    print(
        "Granted scopes:"
    )

    for scope in sorted(
        granted_scopes
    ):
        print(
            f"  {scope}"
        )

    missing_scopes = (
        REQUIRED_READ_SCOPES
        - granted_scopes
    )

    write_scopes = {
        scope
        for scope in granted_scopes
        if scope.startswith(
            "write_"
        )
    }

    unexpected_scopes = (
        granted_scopes
        - REQUIRED_READ_SCOPES
    )

    failed = False

    if missing_scopes:
        failed = True

        print(
            "[FAIL] Missing required scopes: "
            + ", ".join(
                sorted(
                    missing_scopes
                )
            ),
            file=sys.stderr,
        )

    else:
        print(
            "[OK] All required read "
            "scopes are granted"
        )

    if write_scopes:
        failed = True

        print(
            "[FAIL] Write scopes detected: "
            + ", ".join(
                sorted(
                    write_scopes
                )
            ),
            file=sys.stderr,
        )

    else:
        print(
            "[OK] No write scopes detected"
        )

    if unexpected_scopes:
        failed = True

        print(
            "[FAIL] Unexpected scopes detected: "
            + ", ".join(
                sorted(
                    unexpected_scopes
                )
            ),
            file=sys.stderr,
        )

    else:
        print(
            "[OK] No unexpected scopes detected"
        )

    if failed:
        return 1

    print(
        "[PASS] Shopify read-only "
        "connection verified"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )