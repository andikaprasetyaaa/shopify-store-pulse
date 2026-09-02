from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from collectors.products import (
    ProductDataError,
    collect_product_catalog,
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
    variant_id: str,
    product_id: str,
    *,
    variant_title: str,
    sku: str | None,
    inventory_item_id: str,
    product_title: str,
) -> dict[str, Any]:
    return {
        "id":
            variant_id,

        "title":
            variant_title,

        "sku":
            sku,

        "price":
            "25.00",

        "inventoryItem": {
            "id":
                inventory_item_id
        },

        "product": {
            "id":
                product_id,

            "title":
                product_title,

            "handle":
                product_title
                .lower()
                .replace(
                    " ",
                    "-",
                ),

            "status":
                "ACTIVE",

            "vendor":
                "Wooden Ships",

            "productType":
                "Apparel",
        },
    }


def test_collect_product_catalog(
) -> None:
    client = FakeClient(
        {
            "productVariants": {
                "nodes": [
                    make_variant(
                        "variant-1",
                        "product-1",
                        variant_title="Small",
                        sku="SHIRT-S",
                        inventory_item_id=(
                            "inventory-1"
                        ),
                        product_title="Shirt",
                    ),

                    make_variant(
                        "variant-2",
                        "product-1",
                        variant_title="Large",
                        sku="SHIRT-L",
                        inventory_item_id=(
                            "inventory-2"
                        ),
                        product_title="Shirt",
                    ),

                    make_variant(
                        "variant-3",
                        "product-2",
                        variant_title=(
                            "Default Title"
                        ),
                        sku=None,
                        inventory_item_id=(
                            "inventory-3"
                        ),
                        product_title="Hat",
                    ),
                ],

                "pageInfo": {
                    "hasNextPage":
                        False,
                    "endCursor":
                        None,
                },
            }
        }
    )

    catalog = (
        collect_product_catalog(
            client
        )
    )

    assert len(
        catalog["products"]
    ) == 2

    assert len(
        catalog["variants"]
    ) == 3

    assert catalog[
        "products"
    ][0] == {
        "product_id":
            "product-1",

        "title":
            "Shirt",

        "handle":
            "shirt",

        "status":
            "ACTIVE",

        "vendor":
            "Wooden Ships",

        "product_type":
            "Apparel",
    }

    assert catalog[
        "variants"
    ][0] == {
        "variant_id":
            "variant-1",

        "product_id":
            "product-1",

        "title":
            "Small",

        "sku":
            "SHIRT-S",

        "price":
            "25.00",

        "inventory_item_id":
            "inventory-1",
    }


def test_same_product_is_not_duplicated(
) -> None:
    client = FakeClient(
        {
            "productVariants": {
                "nodes": [
                    make_variant(
                        "variant-1",
                        "product-1",
                        variant_title="Small",
                        sku="S",
                        inventory_item_id=(
                            "inventory-1"
                        ),
                        product_title=(
                            "Test Product"
                        ),
                    ),

                    make_variant(
                        "variant-2",
                        "product-1",
                        variant_title="Large",
                        sku="L",
                        inventory_item_id=(
                            "inventory-2"
                        ),
                        product_title=(
                            "Test Product"
                        ),
                    ),
                ],

                "pageInfo": {
                    "hasNextPage":
                        False,
                    "endCursor":
                        None,
                },
            }
        }
    )

    catalog = (
        collect_product_catalog(
            client
        )
    )

    assert len(
        catalog["products"]
    ) == 1

    assert len(
        catalog["variants"]
    ) == 2


def test_max_items_limits_variants(
) -> None:
    client = FakeClient(
        {
            "productVariants": {
                "nodes": [
                    make_variant(
                        "variant-1",
                        "product-1",
                        variant_title="Small",
                        sku="S",
                        inventory_item_id=(
                            "inventory-1"
                        ),
                        product_title="Shirt",
                    ),

                    make_variant(
                        "variant-2",
                        "product-1",
                        variant_title="Large",
                        sku="L",
                        inventory_item_id=(
                            "inventory-2"
                        ),
                        product_title="Shirt",
                    ),

                    make_variant(
                        "variant-3",
                        "product-2",
                        variant_title=(
                            "Default Title"
                        ),
                        sku=None,
                        inventory_item_id=(
                            "inventory-3"
                        ),
                        product_title="Hat",
                    ),
                ],

                "pageInfo": {
                    "hasNextPage":
                        True,
                    "endCursor":
                        "next-page",
                },
            }
        }
    )

    catalog = (
        collect_product_catalog(
            client,
            page_size=100,
            max_items=2,
        )
    )

    assert len(
        catalog["variants"]
    ) == 2

    assert len(
        catalog["products"]
    ) == 1

    assert len(
        client.calls
    ) == 1

    _, variables = (
        client.calls[0]
    )

    assert variables == {
        "first": 2,
        "after": None,
    }


def test_missing_parent_product_is_rejected(
) -> None:
    client = FakeClient(
        {
            "productVariants": {
                "nodes": [
                    {
                        "id":
                            "variant-1",

                        "title":
                            "Small",

                        "sku":
                            "S",

                        "price":
                            "10.00",

                        "inventoryItem": {
                            "id":
                                "inventory-1"
                        },

                        "product":
                            None,
                    }
                ],

                "pageInfo": {
                    "hasNextPage":
                        False,
                    "endCursor":
                        None,
                },
            }
        }
    )

    with pytest.raises(
        ProductDataError,
        match="parent product",
    ):
        collect_product_catalog(
            client
        )


def test_missing_inventory_item_is_rejected(
) -> None:
    client = FakeClient(
        {
            "productVariants": {
                "nodes": [
                    {
                        "id":
                            "variant-1",

                        "title":
                            "Small",

                        "sku":
                            "S",

                        "price":
                            "10.00",

                        "inventoryItem":
                            None,

                        "product": {
                            "id":
                                "product-1",

                            "title":
                                "Product",

                            "handle":
                                "product",

                            "status":
                                "ACTIVE",

                            "vendor":
                                "Vendor",

                            "productType":
                                "Test",
                        },
                    }
                ],

                "pageInfo": {
                    "hasNextPage":
                        False,
                    "endCursor":
                        None,
                },
            }
        }
    )

    with pytest.raises(
        ProductDataError,
        match="inventoryItem",
    ):
        collect_product_catalog(
            client
        )