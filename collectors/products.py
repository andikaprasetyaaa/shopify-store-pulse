from __future__ import annotations

from typing import Any, TypedDict

from shopify.pagination import (
    QueryClient,
    paginate_connection,
)
from shopify.queries import (
    GET_PRODUCT_VARIANTS,
)


class ProductCatalog(TypedDict):
    products: list[dict[str, Any]]
    variants: list[dict[str, Any]]


class ProductDataError(RuntimeError):
    pass


def collect_product_catalog(
    client: QueryClient,
    *,
    page_size: int = 100,
    max_items: int | None = None,
) -> ProductCatalog:
    """
    Collect Shopify products and variants.

    All Shopify communication goes through
    client.query().

    max_items:
        None -> collect the full variant catalog
        N    -> collect at most N variants

    When max_items is used, the returned product
    list represents only the products associated
    with the collected variant sample.
    """

    products_by_id: dict[
        str,
        dict[str, Any],
    ] = {}

    variants: list[
        dict[str, Any]
    ] = []

    nodes = paginate_connection(
        client,
        GET_PRODUCT_VARIANTS,
        "productVariants",
        page_size=page_size,
        max_items=max_items,
    )

    for node in nodes:
        product_record = (
            _normalize_product(
                node
            )
        )

        product_id = product_record[
            "product_id"
        ]

        variant_record = (
            _normalize_variant(
                node,
                product_id,
            )
        )

        existing_product = (
            products_by_id.get(
                product_id
            )
        )

        if existing_product is None:
            products_by_id[
                product_id
            ] = product_record

        elif existing_product != product_record:
            raise ProductDataError(
                f"Product '{product_id}' "
                "returned inconsistent data "
                "across variants."
            )

        variants.append(
            variant_record
        )

    return {
        "products": list(
            products_by_id.values()
        ),
        "variants": variants,
    }


def _normalize_product(
    node: dict[str, Any],
) -> dict[str, Any]:
    product = node.get(
        "product"
    )

    if not isinstance(
        product,
        dict,
    ):
        raise ProductDataError(
            "Product variant is missing "
            "its parent product."
        )

    product_id = _required_string(
        product,
        "id",
        "product",
    )

    return {
        "product_id":
            product_id,

        "title":
            _required_string(
                product,
                "title",
                "product",
            ),

        "handle":
            _required_string(
                product,
                "handle",
                "product",
            ),

        "status":
            _required_string(
                product,
                "status",
                "product",
            ),

        "vendor":
            _optional_string(
                product.get(
                    "vendor"
                )
            ),

        "product_type":
            _optional_string(
                product.get(
                    "productType"
                )
            ),
    }


def _normalize_variant(
    node: dict[str, Any],
    product_id: str,
) -> dict[str, Any]:
    inventory_item = node.get(
        "inventoryItem"
    )

    if not isinstance(
        inventory_item,
        dict,
    ):
        raise ProductDataError(
            "Product variant is missing "
            "inventoryItem."
        )

    return {
        "variant_id":
            _required_string(
                node,
                "id",
                "variant",
            ),

        "product_id":
            product_id,

        "title":
            _required_string(
                node,
                "title",
                "variant",
            ),

        "sku":
            _optional_string(
                node.get(
                    "sku"
                )
            ),

        "price":
            _required_string(
                node,
                "price",
                "variant",
            ),

        "inventory_item_id":
            _required_string(
                inventory_item,
                "id",
                "inventoryItem",
            ),
    }


def _required_string(
    source: dict[str, Any],
    field: str,
    object_name: str,
) -> str:
    value = source.get(
        field
    )

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise ProductDataError(
            f"{object_name}.{field} "
            "is missing or invalid."
        )

    return value


def _optional_string(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        raise ProductDataError(
            "Expected a string "
            "or null value."
        )

    return value