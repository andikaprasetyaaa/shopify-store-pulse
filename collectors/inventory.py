from __future__ import annotations

from typing import Any, TypedDict

from shopify.pagination import (
    QueryClient,
    paginate_connection,
)
from shopify.queries import GET_INVENTORY_VARIANTS


class InventoryCatalog(TypedDict):
    inventory_items: list[dict[str, Any]]
    inventory_levels: list[dict[str, Any]]


class InventoryDataError(RuntimeError):
    """Raised when Shopify inventory data has an invalid structure."""


def collect_inventory(
    client: QueryClient,
    *,
    page_size: int = 100,
    max_items: int | None = None,
) -> InventoryCatalog:
    """
    Collect inventory data from Shopify.

    All Shopify API communication must go through client.query().

    Args:
        client:
            Read-only Shopify query client.

        page_size:
            Number of product variants requested per page.

        max_items:
            None -> collect all variants.
            N    -> collect at most N variants.

    Returns:
        {
            "inventory_items": [...],
            "inventory_levels": [...]
        }
    """

    inventory_items_by_id: dict[str, dict[str, Any]] = {}
    inventory_levels: list[dict[str, Any]] = []

    nodes = paginate_connection(
        client,
        GET_INVENTORY_VARIANTS,
        "productVariants",
        page_size=page_size,
        max_items=max_items,
    )

    for node in nodes:
        variant_id = _required_string(
            node,
            "id",
            "variant",
        )

        sku = _optional_string(
            node.get("sku")
        )

        product = node.get("product")

        if not isinstance(product, dict):
            raise InventoryDataError(
                "Variant is missing parent product."
            )

        product_id = _required_string(
            product,
            "id",
            "product",
        )

        product_title = _required_string(
            product,
            "title",
            "product",
        )

        inventory_item = node.get(
            "inventoryItem"
        )

        if not isinstance(
            inventory_item,
            dict,
        ):
            raise InventoryDataError(
                "Variant is missing inventoryItem."
            )

        inventory_item_id = _required_string(
            inventory_item,
            "id",
            "inventoryItem",
        )

        tracked = _required_bool(
            inventory_item,
            "tracked",
            "inventoryItem",
        )

        inventory_item_record = {
            "inventory_item_id": inventory_item_id,
            "variant_id": variant_id,
            "product_id": product_id,
            "product_title": product_title,
            "sku": sku,
            "tracked": tracked,
        }

        existing_item = inventory_items_by_id.get(
            inventory_item_id
        )

        if existing_item is None:
            inventory_items_by_id[
                inventory_item_id
            ] = inventory_item_record

        elif existing_item != inventory_item_record:
            raise InventoryDataError(
                f"Inventory item '{inventory_item_id}' "
                "returned inconsistent data."
            )

        levels_connection = inventory_item.get(
            "inventoryLevels"
        )

        if not isinstance(
            levels_connection,
            dict,
        ):
            raise InventoryDataError(
                "inventoryItem.inventoryLevels "
                "is missing or invalid."
            )

        _assert_inventory_levels_complete(
            levels_connection,
            inventory_item_id,
        )

        level_nodes = levels_connection.get(
            "nodes"
        )

        if not isinstance(
            level_nodes,
            list,
        ):
            raise InventoryDataError(
                "inventoryItem.inventoryLevels.nodes "
                "is missing or invalid."
            )

        for level in level_nodes:
            if not isinstance(
                level,
                dict,
            ):
                raise InventoryDataError(
                    "Inventory level must be an object."
                )

            normalized_level = (
                _normalize_inventory_level(
                    level=level,
                    inventory_item_id=inventory_item_id,
                    variant_id=variant_id,
                    product_id=product_id,
                    product_title=product_title,
                    sku=sku,
                    tracked=tracked,
                )
            )

            inventory_levels.append(
                normalized_level
            )

    return {
        "inventory_items": list(
            inventory_items_by_id.values()
        ),
        "inventory_levels": inventory_levels,
    }


def _normalize_inventory_level(
    *,
    level: dict[str, Any],
    inventory_item_id: str,
    variant_id: str,
    product_id: str,
    product_title: str,
    sku: str | None,
    tracked: bool,
) -> dict[str, Any]:
    inventory_level_id = _required_string(
        level,
        "id",
        "inventoryLevel",
    )

    location = level.get(
        "location"
    )

    if not isinstance(
        location,
        dict,
    ):
        raise InventoryDataError(
            "Inventory level is missing location."
        )

    location_id = _required_string(
        location,
        "id",
        "location",
    )

    location_name = _required_string(
        location,
        "name",
        "location",
    )

    available = _extract_available_quantity(
        level.get("quantities")
    )

    return {
        "inventory_level_id": inventory_level_id,
        "inventory_item_id": inventory_item_id,
        "variant_id": variant_id,
        "product_id": product_id,
        "product_title": product_title,
        "sku": sku,
        "tracked": tracked,
        "location_id": location_id,
        "location_name": location_name,
        "available": available,
    }


def _extract_available_quantity(
    quantities: Any,
) -> int:
    if not isinstance(
        quantities,
        list,
    ):
        raise InventoryDataError(
            "Inventory quantities are missing or invalid."
        )

    for quantity_record in quantities:
        if not isinstance(
            quantity_record,
            dict,
        ):
            raise InventoryDataError(
                "Inventory quantity must be an object."
            )

        if (
            quantity_record.get("name")
            != "available"
        ):
            continue

        quantity = quantity_record.get(
            "quantity"
        )

        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
        ):
            raise InventoryDataError(
                "Available inventory quantity is invalid."
            )

        return quantity

    raise InventoryDataError(
        "Available inventory quantity was not returned."
    )


def _assert_inventory_levels_complete(
    connection: dict[str, Any],
    inventory_item_id: str,
) -> None:
    """
    GET_INVENTORY_VARIANTS currently requests
    inventoryLevels(first: 250).

    Never silently accept incomplete nested pagination.
    """

    page_info = connection.get(
        "pageInfo"
    )

    if not isinstance(
        page_info,
        dict,
    ):
        raise InventoryDataError(
            "inventoryLevels.pageInfo "
            "is missing or invalid."
        )

    has_next_page = page_info.get(
        "hasNextPage"
    )

    if not isinstance(
        has_next_page,
        bool,
    ):
        raise InventoryDataError(
            "inventoryLevels.hasNextPage "
            "is missing or invalid."
        )

    if has_next_page:
        raise InventoryDataError(
            f"Inventory item '{inventory_item_id}' "
            "has more than 250 inventory levels. "
            "Nested pagination is required."
        )


def _required_string(
    source: dict[str, Any],
    field: str,
    object_name: str,
) -> str:
    value = source.get(
        field
    )

    if (
        not isinstance(value, str)
        or not value
    ):
        raise InventoryDataError(
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
        raise InventoryDataError(
            "Expected string or null."
        )

    return value


def _required_bool(
    source: dict[str, Any],
    field: str,
    object_name: str,
) -> bool:
    value = source.get(
        field
    )

    if not isinstance(
        value,
        bool,
    ):
        raise InventoryDataError(
            f"{object_name}.{field} "
            "is missing or invalid."
        )

    return value