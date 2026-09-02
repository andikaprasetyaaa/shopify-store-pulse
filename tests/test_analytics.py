from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from collectors.analytics import (
    AnalyticsDataError,
    collect_store_pulse_analytics,
    execute_shopifyql,
)


class FakeClient:
    def __init__(
        self,
        responses: list[dict[str, Any]],
    ) -> None:
        self.responses = responses
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

        return self.responses.pop(0)


def make_response(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "shopifyqlQuery": {
            "tableData": {
                "columns": [
                    {
                        "name": "day",
                        "dataType": "DATE",
                        "displayName": "Day",
                    },
                    {
                        "name": "total_sales",
                        "dataType": "MONEY",
                        "displayName": "Total sales",
                    },
                ],
                "rows": rows,
            },
            "parseErrors": [],
        }
    }


def test_execute_shopifyql() -> None:
    client = FakeClient(
        [
            make_response(
                [
                    {
                        "day": "2026-08-31",
                        "total_sales": "1000.00",
                    }
                ]
            )
        ]
    )

    result = execute_shopifyql(
        client,
        """
        FROM sales
        SHOW total_sales
        TIMESERIES day
        SINCE -7d
        """,
    )

    assert result["columns"] == [
        {
            "name": "day",
            "data_type": "DATE",
            "display_name": "Day",
        },
        {
            "name": "total_sales",
            "data_type": "MONEY",
            "display_name": "Total sales",
        },
    ]

    assert result["rows"] == [
        {
            "day": "2026-08-31",
            "total_sales": "1000.00",
        }
    ]


def test_parse_error_is_rejected() -> None:
    client = FakeClient(
        [
            {
                "shopifyqlQuery": {
                    "tableData": None,
                    "parseErrors": [
                        "Invalid metric"
                    ],
                }
            }
        ]
    )

    with pytest.raises(
        AnalyticsDataError,
        match="parse error",
    ):
        execute_shopifyql(
            client,
            "FROM sales SHOW invalid_metric",
        )


def test_empty_query_is_rejected() -> None:
    client = FakeClient([])

    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        execute_shopifyql(
            client,
            "",
        )


def test_store_pulse_runs_two_queries() -> None:
    client = FakeClient(
        [
            make_response([]),

            {
                "shopifyqlQuery": {
                    "tableData": {
                        "columns": [
                            {
                                "name": "day",
                                "dataType": "DATE",
                                "displayName": "Day",
                            },
                            {
                                "name": "sessions",
                                "dataType": "INTEGER",
                                "displayName": "Sessions",
                            },
                        ],
                        "rows": [],
                    },
                    "parseErrors": [],
                }
            },
        ]
    )

    result = (
        collect_store_pulse_analytics(
            client
        )
    )

    assert "sales_daily" in result
    assert "sessions_daily" in result

    assert len(
        client.calls
    ) == 2

    first_query = (
        client.calls[0][1][
            "shopifyql"
        ]
    )

    second_query = (
        client.calls[1][1][
            "shopifyql"
        ]
    )

    assert "FROM sales" in first_query
    assert "total_sales" in first_query

    assert "FROM sessions" in second_query
    assert "conversion_rate" in second_query