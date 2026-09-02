from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict

from shopify.pagination import (
    QueryClient,
    paginate_connection,
)
from shopify.queries import GET_ORDERS


class OrderCatalog(TypedDict):
    orders: list[dict[str, Any]]
    line_items: list[dict[str, Any]]


class OrderDataError(RuntimeError):
    """Raised when Shopify order data has an invalid structure."""


def collect_orders(
    client: QueryClient,
    *,
    page_size: int = 50,
    max_items: int | None = None,
    query_filter: str | None = None,
) -> OrderCatalog:
    """
    Collect orders and order line items from Shopify.

    All Shopify communication goes through client.query().

    Args:
        client:
            Read-only Shopify query client.

        page_size:
            Number of orders requested per GraphQL page.

        max_items:
            None -> collect all accessible orders.
            N    -> collect at most N orders.

        query_filter:
            Optional Shopify order search query.

            Examples:
                "financial_status:paid"

                "created_at:>=2026-08-01"

    Returns:
        {
            "orders": [...],
            "line_items": [...]
        }

    This collector performs normalization only.
    It does not calculate revenue, AOV, baselines,
    anomalies, or other business metrics.
    """

    orders: list[dict[str, Any]] = []
    line_items: list[dict[str, Any]] = []

    nodes = paginate_connection(
        client,
        GET_ORDERS,
        "orders",
        variables={
            "query": query_filter,
        },
        page_size=page_size,
        max_items=max_items,
    )

    for node in nodes:
        order_record = _normalize_order(
            node
        )

        orders.append(
            order_record
        )

        order_id = order_record[
            "order_id"
        ]

        order_name = order_record[
            "order_name"
        ]

        lines_connection = node.get(
            "lineItems"
        )

        if not isinstance(
            lines_connection,
            dict,
        ):
            raise OrderDataError(
                f"Order '{order_id}' "
                "is missing lineItems."
            )

        _assert_line_items_complete(
            lines_connection,
            order_id,
        )

        line_nodes = lines_connection.get(
            "nodes"
        )

        if not isinstance(
            line_nodes,
            list,
        ):
            raise OrderDataError(
                f"Order '{order_id}' "
                "lineItems.nodes is missing "
                "or invalid."
            )

        for line_node in line_nodes:
            if not isinstance(
                line_node,
                dict,
            ):
                raise OrderDataError(
                    f"Order '{order_id}' "
                    "returned a non-object "
                    "line item."
                )

            line_items.append(
                _normalize_line_item(
                    line_node,
                    order_id=order_id,
                    order_name=order_name,
                )
            )

    return {
        "orders": orders,
        "line_items": line_items,
    }


def _normalize_order(
    node: dict[str, Any],
) -> dict[str, Any]:
    order_id = _required_string(
        node,
        "id",
        "order",
    )

    order_name = _required_string(
        node,
        "name",
        "order",
    )

    created_at = _required_string(
        node,
        "createdAt",
        "order",
    )

    updated_at = _required_string(
        node,
        "updatedAt",
        "order",
    )

    cancelled_at = _optional_string(
        node.get(
            "cancelledAt"
        )
    )

    financial_status = _optional_string(
        node.get(
            "displayFinancialStatus"
        )
    )

    fulfillment_status = _required_string(
        node,
        "displayFulfillmentStatus",
        "order",
    )

    total_amount, currency_code = (
        _extract_shop_money(
            node.get(
                "totalPriceSet"
            ),
            "order.totalPriceSet",
        )
    )

    return {
        "order_id":
            order_id,

        "order_name":
            order_name,

        "created_at":
            created_at,

        "updated_at":
            updated_at,

        "cancelled_at":
            cancelled_at,

        "financial_status":
            financial_status,

        "fulfillment_status":
            fulfillment_status,

        "total_price":
            total_amount,

        "currency_code":
            currency_code,
    }


def _normalize_line_item(
    node: dict[str, Any],
    *,
    order_id: str,
    order_name: str,
) -> dict[str, Any]:
    line_item_id = _required_string(
        node,
        "id",
        "lineItem",
    )

    name = _required_string(
        node,
        "name",
        "lineItem",
    )

    title = _required_string(
        node,
        "title",
        "lineItem",
    )

    sku = _optional_string(
        node.get(
            "sku"
        )
    )

    quantity = _required_int(
        node,
        "quantity",
        "lineItem",
    )

    current_quantity = _required_int(
        node,
        "currentQuantity",
        "lineItem",
    )

    product_id = _extract_optional_id(
        node.get(
            "product"
        ),
        "product",
    )

    variant_id = _extract_optional_id(
        node.get(
            "variant"
        ),
        "variant",
    )

    original_total, original_currency = (
        _extract_shop_money(
            node.get(
                "originalTotalSet"
            ),
            "lineItem.originalTotalSet",
        )
    )

    (
        current_discounted_total,
        current_discounted_currency,
    ) = _extract_shop_money(
        node.get(
            "priceAfterAllDiscountsBeforeTaxesSet"
        ),
        (
            "lineItem."
            "priceAfterAllDiscountsBeforeTaxesSet"
        ),
    )

    if (
        original_currency
        != current_discounted_currency
    ):
        raise OrderDataError(
            f"Line item '{line_item_id}' "
            "returned inconsistent shop "
            "currency values."
        )

    return {
        "line_item_id":
            line_item_id,

        "order_id":
            order_id,

        "order_name":
            order_name,

        "product_id":
            product_id,

        "variant_id":
            variant_id,

        "name":
            name,

        "title":
            title,

        "sku":
            sku,

        "quantity":
            quantity,

        "current_quantity":
            current_quantity,

        "original_total":
            original_total,

        "current_discounted_total":
            current_discounted_total,

        "currency_code":
            original_currency,
    }


def _extract_shop_money(
    money_set: Any,
    object_name: str,
) -> tuple[str, str]:
    if not isinstance(
        money_set,
        dict,
    ):
        raise OrderDataError(
            f"{object_name} "
            "is missing or invalid."
        )

    shop_money = money_set.get(
        "shopMoney"
    )

    if not isinstance(
        shop_money,
        dict,
    ):
        raise OrderDataError(
            f"{object_name}.shopMoney "
            "is missing or invalid."
        )

    amount = shop_money.get(
        "amount"
    )

    currency_code = shop_money.get(
        "currencyCode"
    )

    if (
        not isinstance(
            amount,
            str,
        )
        or not amount
    ):
        raise OrderDataError(
            f"{object_name}.shopMoney.amount "
            "is missing or invalid."
        )

    try:
        Decimal(amount)

    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise OrderDataError(
            f"{object_name}.shopMoney.amount "
            "is not a valid decimal value."
        ) from exc

    if (
        not isinstance(
            currency_code,
            str,
        )
        or not currency_code
    ):
        raise OrderDataError(
            f"{object_name}.shopMoney.currencyCode "
            "is missing or invalid."
        )

    return (
        amount,
        currency_code,
    )


def _extract_optional_id(
    value: Any,
    object_name: str,
) -> str | None:
    """
    Product and variant can legitimately be null.

    For example, historical order data can remain
    after the original catalog object was removed.
    """

    if value is None:
        return None

    if not isinstance(
        value,
        dict,
    ):
        raise OrderDataError(
            f"lineItem.{object_name} "
            "is invalid."
        )

    object_id = value.get(
        "id"
    )

    if (
        not isinstance(
            object_id,
            str,
        )
        or not object_id
    ):
        raise OrderDataError(
            f"lineItem.{object_name}.id "
            "is missing or invalid."
        )

    return object_id


def _assert_line_items_complete(
    connection: dict[str, Any],
    order_id: str,
) -> None:
    """
    GET_ORDERS currently requests
    lineItems(first: 250).

    Never silently accept a partially collected
    order. If an order has more than 250 line
    items, nested pagination must be implemented.
    """

    page_info = connection.get(
        "pageInfo"
    )

    if not isinstance(
        page_info,
        dict,
    ):
        raise OrderDataError(
            f"Order '{order_id}' "
            "lineItems.pageInfo is "
            "missing or invalid."
        )

    has_next_page = page_info.get(
        "hasNextPage"
    )

    if not isinstance(
        has_next_page,
        bool,
    ):
        raise OrderDataError(
            f"Order '{order_id}' "
            "lineItems.hasNextPage is "
            "missing or invalid."
        )

    if has_next_page:
        raise OrderDataError(
            f"Order '{order_id}' has more "
            "than 250 line items. "
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
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise OrderDataError(
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
        raise OrderDataError(
            "Expected string or null."
        )

    return value


def _required_int(
    source: dict[str, Any],
    field: str,
    object_name: str,
) -> int:
    value = source.get(
        field
    )

    if (
        not isinstance(
            value,
            int,
        )
        or isinstance(
            value,
            bool,
        )
    ):
        raise OrderDataError(
            f"{object_name}.{field} "
            "is missing or invalid."
        )

    if value < 0:
        raise OrderDataError(
            f"{object_name}.{field} "
            "cannot be negative."
        )

    return value