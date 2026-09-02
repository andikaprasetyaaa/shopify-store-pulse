from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from collectors.orders import (
    OrderDataError,
    collect_orders,
)


class FakeClient:
    def __init__(
        self,
        response: dict[str, Any],
    ) -> None:
        self.response = response

        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def query(
        self,
        document: str,
        variables: Mapping[str, Any] | None = None,
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


def make_money(
    amount: str,
    currency: str = "USD",
) -> dict[str, Any]:
    return {
        "shopMoney": {
            "amount": amount,
            "currencyCode": currency,
        }
    }


def make_line_item(
    *,
    line_item_id: str = "line-1",
    product_id: str | None = "product-1",
    variant_id: str | None = "variant-1",
    name: str = "Shirt - Small",
    title: str = "Shirt",
    sku: str | None = "SHIRT-S",
    quantity: int = 2,
    current_quantity: int = 2,
    original_total: str = "50.00",
    discounted_total: str = "45.00",
) -> dict[str, Any]:
    return {
        "id": line_item_id,
        "name": name,
        "title": title,
        "sku": sku,
        "quantity": quantity,
        "currentQuantity": current_quantity,

        "product": (
            {"id": product_id}
            if product_id is not None
            else None
        ),

        "variant": (
            {"id": variant_id}
            if variant_id is not None
            else None
        ),

        "originalTotalSet": make_money(
            original_total
        ),

        "priceAfterAllDiscountsBeforeTaxesSet":
            make_money(
                discounted_total
            ),
    }


def make_order(
    *,
    order_id: str = "order-1",
    order_name: str = "#1001",
    line_items: list[dict[str, Any]] | None = None,
    line_items_has_next_page: bool = False,
) -> dict[str, Any]:
    if line_items is None:
        line_items = [
            make_line_item()
        ]

    return {
        "id": order_id,
        "name": order_name,

        "createdAt":
            "2026-08-31T10:00:00Z",

        "updatedAt":
            "2026-08-31T10:05:00Z",

        "cancelledAt":
            None,

        "displayFinancialStatus":
            "PAID",

        "displayFulfillmentStatus":
            "FULFILLED",

        "totalPriceSet":
            make_money("50.00"),

        "lineItems": {
            "nodes":
                line_items,

            "pageInfo": {
                "hasNextPage":
                    line_items_has_next_page,

                "endCursor":
                    (
                        "next-line-page"
                        if line_items_has_next_page
                        else None
                    ),
            },
        },
    }


def make_response(
    orders: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
) -> dict[str, Any]:
    return {
        "orders": {
            "nodes":
                orders,

            "pageInfo": {
                "hasNextPage":
                    has_next_page,

                "endCursor":
                    (
                        "next-order-page"
                        if has_next_page
                        else None
                    ),
            },
        }
    }


def test_collect_orders() -> None:
    client = FakeClient(
        make_response(
            [
                make_order()
            ]
        )
    )

    catalog = collect_orders(
        client
    )

    assert catalog["orders"] == [
        {
            "order_id":
                "order-1",

            "order_name":
                "#1001",

            "created_at":
                "2026-08-31T10:00:00Z",

            "updated_at":
                "2026-08-31T10:05:00Z",

            "cancelled_at":
                None,

            "financial_status":
                "PAID",

            "fulfillment_status":
                "FULFILLED",

            "total_price":
                "50.00",

            "currency_code":
                "USD",
        }
    ]

    assert catalog["line_items"] == [
        {
            "line_item_id":
                "line-1",

            "order_id":
                "order-1",

            "order_name":
                "#1001",

            "product_id":
                "product-1",

            "variant_id":
                "variant-1",

            "name":
                "Shirt - Small",

            "title":
                "Shirt",

            "sku":
                "SHIRT-S",

            "quantity":
                2,

            "current_quantity":
                2,

            "original_total":
                "50.00",

            "current_discounted_total":
                "45.00",

            "currency_code":
                "USD",
        }
    ]


def test_multiple_line_items_are_collected() -> None:
    order = make_order(
        line_items=[
            make_line_item(
                line_item_id="line-1",
                variant_id="variant-1",
                sku="SHIRT-S",
            ),

            make_line_item(
                line_item_id="line-2",
                variant_id="variant-2",
                sku="SHIRT-L",
                name="Shirt - Large",
            ),
        ]
    )

    client = FakeClient(
        make_response(
            [order]
        )
    )

    catalog = collect_orders(
        client
    )

    assert len(
        catalog["orders"]
    ) == 1

    assert len(
        catalog["line_items"]
    ) == 2

    assert [
        item["line_item_id"]
        for item in catalog["line_items"]
    ] == [
        "line-1",
        "line-2",
    ]


def test_deleted_product_and_variant_can_be_null(
) -> None:
    order = make_order(
        line_items=[
            make_line_item(
                product_id=None,
                variant_id=None,
            )
        ]
    )

    client = FakeClient(
        make_response(
            [order]
        )
    )

    catalog = collect_orders(
        client
    )

    line = catalog[
        "line_items"
    ][0]

    assert line["product_id"] is None
    assert line["variant_id"] is None


def test_max_items_is_forwarded_to_pagination(
) -> None:
    client = FakeClient(
        make_response(
            [
                make_order(
                    order_id="order-1",
                    order_name="#1001",
                ),
                make_order(
                    order_id="order-2",
                    order_name="#1002",
                ),
            ],
            has_next_page=True,
        )
    )

    catalog = collect_orders(
        client,
        page_size=50,
        max_items=1,
    )

    assert len(
        catalog["orders"]
    ) == 1

    assert len(
        client.calls
    ) == 1

    document, variables = (
        client.calls[0]
    )

    assert "orders" in document

    assert variables == {
        "query": None,
        "first": 1,
        "after": None,
    }


def test_query_filter_is_forwarded() -> None:
    client = FakeClient(
        make_response([])
    )

    collect_orders(
        client,
        query_filter=(
            "financial_status:paid"
        ),
    )

    _, variables = (
        client.calls[0]
    )

    assert variables["query"] == (
        "financial_status:paid"
    )


def test_more_than_250_line_items_is_not_silently_ignored(
) -> None:
    order = make_order(
        line_items_has_next_page=True
    )

    client = FakeClient(
        make_response(
            [order]
        )
    )

    with pytest.raises(
        OrderDataError,
        match="more than 250 line items",
    ):
        collect_orders(
            client
        )


def test_invalid_order_money_is_rejected() -> None:
    order = make_order()

    order["totalPriceSet"] = (
        make_money(
            "not-a-number"
        )
    )

    client = FakeClient(
        make_response(
            [order]
        )
    )

    with pytest.raises(
        OrderDataError,
        match="valid decimal",
    ):
        collect_orders(
            client
        )


def test_currency_mismatch_is_rejected() -> None:
    line = make_line_item()

    line[
        "priceAfterAllDiscountsBeforeTaxesSet"
    ] = make_money(
        "45.00",
        "EUR",
    )

    order = make_order(
        line_items=[line]
    )

    client = FakeClient(
        make_response(
            [order]
        )
    )

    with pytest.raises(
        OrderDataError,
        match="inconsistent shop currency",
    ):
        collect_orders(
            client
        )