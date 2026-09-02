from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from api.deps import DashboardDataError
from services.trends import (
    build_trend,
    filled_daily_series,
    summarize_period,
)


def make_row(
    day: str,
    *,
    revenue: str = "100.00",
    orders: int = 10,
    units: int = 20,
    currency: str = "USD",
) -> dict:
    """
    Mirrors one row of
    StorePulseMetrics.daily_order_metrics().
    """

    return {
        "day": day,
        "revenue": revenue,
        "orders": orders,
        "aov": (
            str(
                float(revenue) / orders
            )
            if orders
            else "0"
        ),
        "units_sold": units,
        "currency_code": currency,
    }


def test_mixed_currencies_are_rejected() -> None:
    """
    Summing USD and EUR into one revenue figure would
    be silently wrong, so it must raise instead.
    """

    with pytest.raises(
        DashboardDataError
    ):
        filled_daily_series(
            [
                make_row(
                    "2026-09-01",
                    currency="USD",
                ),
                make_row(
                    "2026-09-02",
                    currency="EUR",
                ),
            ]
        )


def test_empty_input_gives_empty_series() -> None:
    assert filled_daily_series([]) == []


def test_missing_days_are_filled_with_zeroes() -> None:
    """
    A store with no orders on a day must still get a
    point on the chart, otherwise the line silently
    skips the gap and the trend looks wrong.
    """

    series = filled_daily_series(
        [
            make_row("2026-09-01"),
            # 09-02 and 09-03 have no orders
            make_row("2026-09-04"),
        ]
    )

    days = [
        row["day"] for row in series
    ]

    assert days == [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]

    assert series[1]["orders"] == 0
    assert series[1]["revenue"] == Decimal("0")


def test_single_day_series() -> None:
    series = filled_daily_series(
        [make_row("2026-09-01")]
    )

    assert len(series) == 1
    assert series[0]["orders"] == 10


def test_summarize_period_totals() -> None:
    rows = filled_daily_series(
        [
            make_row(
                "2026-09-01",
                revenue="100.00",
                orders=10,
                units=20,
            ),
            make_row(
                "2026-09-02",
                revenue="300.00",
                orders=30,
                units=40,
            ),
        ]
    )

    summary = summarize_period(rows)

    # summarize_period already runs values through
    # number(), so the payload is JSON-ready floats.
    assert summary["revenue"] == 400.0
    assert summary["orders"] == 40
    assert summary["units_sold"] == 60
    assert summary["start"] == "2026-09-01"
    assert summary["end"] == "2026-09-02"


def test_summarize_period_average_order_value() -> None:
    rows = filled_daily_series(
        [
            make_row(
                "2026-09-01",
                revenue="200.00",
                orders=10,
            ),
        ]
    )

    summary = summarize_period(rows)

    assert summary["aov"] == 20.0


def test_summarize_period_survives_zero_orders() -> None:
    """
    A period with no orders must not divide by zero
    when computing average order value.
    """

    rows = filled_daily_series(
        [
            make_row(
                "2026-09-01",
                revenue="0.00",
                orders=0,
                units=0,
            ),
        ]
    )

    summary = summarize_period(rows)

    assert summary["orders"] == 0
    assert summary["revenue"] == 0.0
    assert summary["aov"] == 0.0


def build_days(
    count: int,
    *,
    revenue: str = "100.00",
) -> list[dict]:
    start = date(2026, 8, 1)

    return filled_daily_series(
        [
            make_row(
                (
                    start
                    + timedelta(days=offset)
                ).isoformat(),
                revenue=revenue,
            )
            for offset in range(count)
        ]
    )


def test_trend_has_no_baseline_for_first_week() -> None:
    """
    The 7-day baseline needs 7 prior days, so the
    first week must report None rather than a
    baseline computed from fewer days.
    """

    trend = build_trend(
        build_days(10),
        10,
    )

    for point in trend[:7]:
        assert point["baseline_7d"] is None

    assert trend[7]["baseline_7d"] is not None


def test_trend_baseline_is_average_of_prior_week() -> None:
    trend = build_trend(
        build_days(8, revenue="70.00"),
        8,
    )

    assert float(
        trend[7]["baseline_7d"]
    ) == 70.0


def test_trend_returns_only_requested_days() -> None:
    trend = build_trend(
        build_days(30),
        7,
    )

    assert len(trend) == 7


def test_trend_keeps_chronological_order() -> None:
    trend = build_trend(
        build_days(14),
        14,
    )

    days = [
        point["day"] for point in trend
    ]

    assert days == sorted(days)
