from __future__ import annotations

"""
Daily order series and period comparison.

Turns the raw daily metrics from analytics.metrics
into the gap-free series and period-over-period
summaries the dashboard renders.

No FastAPI and no HTTP concerns here, so this can be
tested directly against a DuckDB fixture.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from api.deps import (
    DashboardDataError,
)


def filled_daily_series(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        return []

    mapped: dict[
        date,
        dict[str, Any],
    ] = {}

    currencies: set[str] = set()

    for row in rows:
        metric_day = date.fromisoformat(
            row["day"]
        )

        currency = row.get(
            "currency_code"
        )

        if currency:
            currencies.add(
                str(currency)
            )

        mapped[
            metric_day
        ] = {
            "day":
                metric_day,

            "revenue":
                Decimal(
                    str(
                        row["revenue"]
                    )
                ),

            "orders":
                int(
                    row["orders"]
                ),

            "aov":
                Decimal(
                    str(
                        row["aov"]
                    )
                ),

            "units_sold":
                int(
                    row["units_sold"]
                ),

            "currency_code":
                currency,
        }

    if len(currencies) > 1:
        raise DashboardDataError(
            "Multiple currencies detected."
        )

    currency_code = (
        next(iter(currencies))
        if currencies
        else None
    )

    first_day = min(
        mapped
    )

    last_day = max(
        mapped
    )

    result: list[
        dict[str, Any]
    ] = []

    current_day = first_day

    while current_day <= last_day:
        existing = mapped.get(
            current_day
        )

        if existing is None:
            result.append(
                {
                    "day":
                        current_day,

                    "revenue":
                        Decimal("0"),

                    "orders":
                        0,

                    "aov":
                        Decimal("0"),

                    "units_sold":
                        0,

                    "currency_code":
                        currency_code,
                }
            )

        else:
            result.append(
                existing
            )

        current_day += timedelta(
            days=1
        )

    return result


def summarize_period(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    revenue = sum(
        (
            row["revenue"]
            for row in rows
        ),
        Decimal("0"),
    )

    orders = sum(
        row["orders"]
        for row in rows
    )

    units = sum(
        row["units_sold"]
        for row in rows
    )

    aov = (
        revenue
        / Decimal(orders)
        if orders
        else Decimal("0")
    )

    currency_code = (
        rows[-1][
            "currency_code"
        ]
        if rows
        else None
    )

    return {
        "revenue":
            round(
                float(revenue),
                2,
            ),

        "orders":
            orders,

        "aov":
            round(
                float(aov),
                2,
            ),

        "units_sold":
            units,

        "currency_code":
            currency_code,

        "start":
            (
                rows[0][
                    "day"
                ].isoformat()
                if rows
                else None
            ),

        "end":
            (
                rows[-1][
                    "day"
                ].isoformat()
                if rows
                else None
            ),
    }


def build_trend(
    rows: list[dict[str, Any]],
    days: int,
) -> list[dict[str, Any]]:
    enriched: list[
        dict[str, Any]
    ] = []

    for index, row in enumerate(
        rows
    ):
        baseline = None

        if index >= 7:
            previous = rows[
                index - 7:
                index
            ]

            total = sum(
                (
                    item[
                        "revenue"
                    ]
                    for item
                    in previous
                ),
                Decimal("0"),
            )

            baseline = (
                total
                / Decimal("7")
            )

        enriched.append(
            {
                "day":
                    row[
                        "day"
                    ].isoformat(),

                "revenue":
                    round(
                        float(
                            row[
                                "revenue"
                            ]
                        ),
                        2,
                    ),

                "orders":
                    row[
                        "orders"
                    ],

                "aov":
                    round(
                        float(
                            row[
                                "aov"
                            ]
                        ),
                        2,
                    ),

                "units_sold":
                    row[
                        "units_sold"
                    ],

                "baseline_7d":
                    (
                        round(
                            float(
                                baseline
                            ),
                            2,
                        )
                        if baseline
                        is not None
                        else None
                    ),
            }
        )

    return enriched[
        -days:
    ]
