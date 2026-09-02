from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from collectors.inventory import (
    InventoryDataError,
    collect_inventory,
)


class FakeClient:
    def __init__(
        self,
        response: dict[str, Any],
    ) -> None:
        self.response = response

        self.calls: list[
            tuple[
                str,
                dict[str, Any],
            ]
        ] = []

    def query(
        self,
        document: str,
        variables: Mapping[
            str,
            Any,
        ] | None = None,
    ) -> dict[str, Any]:

        values = dict(
            variables or {}
        )

        self.calls.append(
            (
                document,
                values,
            )
        )

        return self.response


def make_variant(
    *,
    variant_id: str = "variant-1",
    product_id: str = "product-1",
    product_title: str = "Shirt",
    sku: str | None = "SHIRT-S",
    inventory_item_id: str = "inventory-1",
    tracked: bool = True,
    levels: list[dict[str, Any]] | None = None,
    levels_has_next_page: bool = False,
) -> dict[str, Any]:

    if levels is None:
        levels = [
            {
                "id": "level-1",

                "location": {
                    "id": "location-1",
                    "name": "Warehouse",
                },

                "quantities": [
                    {
                        "name": "available",
                        "quantity": 25,
                    }
                ],
            }
        ]

    return {
        "id":
            variant_id,

        "sku":
            sku,

        "product": {
            "id":
                product_id,

            "title":
                product_title,
        },

        "inventoryItem": {
            "id":
                inventory_item_id,

            "tracked":
                tracked,

            "inventoryLevels": {
                "nodes":
                    levels,

                "pageInfo": {
                    "hasNextPage":
                        levels_has_next_page,

                    "endCursor":
                        (
                            "next-level-page"
                            if levels_has_next_page
                            else None
                        ),
                },
            },
        },
    }


def make_response(
    variants: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
) -> dict[str, Any]:

    return {
        "productVariants": {
            "nodes":
                variants,

            "pageInfo": {
                "hasNextPage":
                    has_next_page,

                "endCursor":
                    (
                        "next-page"
                        if has_next_page
                        else None
                    ),
            },
        }
    }


def test_collect_inventory(
) -> None:

    client = FakeClient(
        make_response(
            [
                make_variant()
            ]
        )
    )

    catalog = collect_inventory(
        client
    )

    assert catalog[
        "inventory_items"
    ] == [
        {
            "inventory_item_id":
                "inventory-1",

            "variant_id":
                "variant-1",

            "product_id":
                "product-1",

            "product_title":
                "Shirt",

            "sku":
                "SHIRT-S",

            "tracked":
                True,
        }
    ]

    assert catalog[
        "inventory_levels"
    ] == [
        {
            "inventory_level_id":
                "level-1",

            "inventory_item_id":
                "inventory-1",

            "variant_id":
                "variant-1",

            "product_id":
                "product-1",

            "product_title":
                "Shirt",

            "sku":
                "SHIRT-S",

            "tracked":
                True,

            "location_id":
                "location-1",

            "location_name":
                "Warehouse",

            "available":
                25,
        }
    ]


def test_multiple_locations_are_collected(
) -> None:

    variant = make_variant(
        levels=[
            {
                "id": "level-1",

                "location": {
                    "id": "location-1",
                    "name": "Warehouse",
                },

                "quantities": [
                    {
                        "name": "available",
                        "quantity": 10,
                    }
                ],
            },

            {
                "id": "level-2",

                "location": {
                    "id": "location-2",
                    "name": "Retail Store",
                },

                "quantities": [
                    {
                        "name": "available",
                        "quantity": 5,
                    }
                ],
            },
        ]
    )

    client = FakeClient(
        make_response(
            [variant]
        )
    )

    catalog = collect_inventory(
        client
    )

    assert len(
        catalog[
            "inventory_items"
        ]
    ) == 1

    assert len(
        catalog[
            "inventory_levels"
        ]
    ) == 2

    assert [
        level["available"]
        for level in catalog[
            "inventory_levels"
        ]
    ] == [
        10,
        5,
    ]


def test_max_items_is_forwarded_to_pagination(
) -> None:

    client = FakeClient(
        make_response(
            [
                make_variant(),
                make_variant(
                    variant_id="variant-2",
                    inventory_item_id="inventory-2",
                    sku="SHIRT-L",
                ),
            ],
            has_next_page=True,
        )
    )

    catalog = collect_inventory(
        client,
        page_size=20,
        max_items=1,
    )

    assert len(
        catalog[
            "inventory_items"
        ]
    ) == 1

    assert len(
        client.calls
    ) == 1

    _, variables = (
        client.calls[0]
    )

    assert variables == {
        "first": 1,
        "after": None,
    }


def test_missing_inventory_item_is_rejected(
) -> None:

    variant = make_variant()

    variant[
        "inventoryItem"
    ] = None

    client = FakeClient(
        make_response(
            [variant]
        )
    )

    with pytest.raises(
        InventoryDataError,
        match="inventoryItem",
    ):
        collect_inventory(
            client
        )


def test_missing_available_quantity_is_rejected(
) -> None:

    variant = make_variant(
        levels=[
            {
                "id": "level-1",

                "location": {
                    "id": "location-1",
                    "name": "Warehouse",
                },

                "quantities": [
                    {
                        "name": "on_hand",
                        "quantity": 20,
                    }
                ],
            }
        ]
    )

    client = FakeClient(
        make_response(
            [variant]
        )
    )

    with pytest.raises(
        InventoryDataError,
        match="Available inventory",
    ):
        collect_inventory(
            client
        )


def test_nested_inventory_pagination_is_not_silently_ignored(
) -> None:

    variant = make_variant(
        levels_has_next_page=True
    )

    client = FakeClient(
        make_response(
            [variant]
        )
    )

    with pytest.raises(
        InventoryDataError,
        match="more than 250",
    ):
        collect_inventory(
            client
        )