from __future__ import annotations

from typing import Any, TypedDict

from shopify.pagination import QueryClient
from shopify.queries import RUN_SHOPIFYQL


class ShopifyQLResult(TypedDict):
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]


class StorePulseAnalytics(TypedDict):
    sales_daily: ShopifyQLResult
    sessions_daily: ShopifyQLResult


class AnalyticsDataError(RuntimeError):
    pass


SALES_DAILY_QUERY = """
FROM sales
SHOW total_sales, orders
TIMESERIES day
SINCE -60d UNTIL today
ORDER BY day ASC
""".strip()


SESSIONS_DAILY_QUERY = """
FROM sessions
SHOW sessions, conversion_rate,
  online_store_visitors,
  sessions_with_cart_additions,
  sessions_that_reached_checkout,
  sessions_that_completed_checkout
TIMESERIES day
SINCE -60d UNTIL today
ORDER BY day ASC
""".strip()


def execute_shopifyql(
    client: QueryClient,
    shopifyql_query: str,
) -> ShopifyQLResult:
    """
    Execute a read-only ShopifyQL query.

    Shopify communication always goes through
    client.query().
    """

    if (
        not isinstance(shopifyql_query, str)
        or not shopifyql_query.strip()
    ):
        raise ValueError(
            "ShopifyQL query cannot be empty."
        )

    data = client.query(
        RUN_SHOPIFYQL,
        {
            "shopifyql":
                shopifyql_query.strip(),
        },
    )

    response = data.get(
        "shopifyqlQuery"
    )

    if not isinstance(
        response,
        dict,
    ):
        raise AnalyticsDataError(
            "ShopifyQL response is missing."
        )

    parse_errors = response.get(
        "parseErrors"
    )

    if not isinstance(
        parse_errors,
        list,
    ):
        raise AnalyticsDataError(
            "ShopifyQL parseErrors is invalid."
        )

    if parse_errors:
        error_messages = [
            str(error)
            for error in parse_errors
        ]

        raise AnalyticsDataError(
            "ShopifyQL parse error: "
            + "; ".join(error_messages)
        )

    table_data = response.get(
        "tableData"
    )

    if not isinstance(
        table_data,
        dict,
    ):
        raise AnalyticsDataError(
            "ShopifyQL tableData is missing."
        )

    raw_columns = table_data.get(
        "columns"
    )

    raw_rows = table_data.get(
        "rows"
    )

    if not isinstance(
        raw_columns,
        list,
    ):
        raise AnalyticsDataError(
            "ShopifyQL columns are invalid."
        )

    if not isinstance(
        raw_rows,
        list,
    ):
        raise AnalyticsDataError(
            "ShopifyQL rows are invalid."
        )

    columns: list[
        dict[str, str]
    ] = []

    for column in raw_columns:
        if not isinstance(
            column,
            dict,
        ):
            raise AnalyticsDataError(
                "ShopifyQL column must be an object."
            )

        name = _required_string(
            column,
            "name",
            "column",
        )

        data_type = _required_string(
            column,
            "dataType",
            "column",
        )

        display_name = _required_string(
            column,
            "displayName",
            "column",
        )

        columns.append(
            {
                "name": name,
                "data_type": data_type,
                "display_name": display_name,
            }
        )

    rows: list[
        dict[str, Any]
    ] = []

    for row in raw_rows:
        if not isinstance(
            row,
            dict,
        ):
            raise AnalyticsDataError(
                "ShopifyQL row must be an object."
            )

        rows.append(
            dict(row)
        )

    return {
        "columns": columns,
        "rows": rows,
    }


def collect_store_pulse_analytics(
    client: QueryClient,
) -> StorePulseAnalytics:
    """
    Collect the first Shopify Store Pulse
    analytics datasets.

    No KPI calculations or anomaly detection
    are performed here.
    """

    sales_daily = execute_shopifyql(
        client,
        SALES_DAILY_QUERY,
    )

    sessions_daily = execute_shopifyql(
        client,
        SESSIONS_DAILY_QUERY,
    )

    return {
        "sales_daily": sales_daily,
        "sessions_daily": sessions_daily,
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
        not isinstance(value, str)
        or not value
    ):
        raise AnalyticsDataError(
            f"{object_name}.{field} "
            "is missing or invalid."
        )

    return value