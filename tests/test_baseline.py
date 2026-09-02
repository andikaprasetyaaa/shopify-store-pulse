from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from analytics.baseline import (
    BaselineError,
    StorePulseBaselines,
)


class FakeMetrics:
    def __init__(
        self,
        rows: list[dict],
    ) -> None:
        self.rows = rows

    def daily_order_metrics(
        self,
        *,
        start_at=None,
        end_at=None,
        exclude_cancelled=True,
    ):
        return self.rows


def make_daily_rows(
    *,
    start_day: date,
    days: int,
    revenue: Decimal = Decimal("100"),
    orders: int = 10,
    aov: Decimal = Decimal("10"),
    units_sold: int = 20,
) -> list[dict]:
    rows: list[dict] = []

    for offset in range(days):
        current_day = (
            start_day
            + timedelta(days=offset)
        )

        rows.append(
            {
                "day":
                    current_day.isoformat(),

                "revenue":
                    revenue,

                "orders":
                    orders,

                "aov":
                    aov,

                "units_sold":
                    units_sold,

                "currency_code":
                    "USD",
            }
        )

    return rows


def test_rolling_baselines_exclude_current_day(
) -> None:
    start_day = date(
        2026,
        8,
        1,
    )

    rows = make_daily_rows(
        start_day=start_day,
        days=30,
        revenue=Decimal("100"),
    )

    # Make current day a large spike.
    rows[-1][
        "revenue"
    ] = Decimal("1000")

    metrics = FakeMetrics(
        rows
    )

    baseline = StorePulseBaselines(
        metrics
    )

    result = (
        baseline.order_metric_baseline(
            "revenue"
        )
    )

    assert result[
        "current_value"
    ] == Decimal("1000")

    assert result[
        "avg_7d"
    ] == Decimal("100")

    assert result[
        "avg_14d"
    ] == Decimal("100")

    assert result[
        "avg_28d"
    ] == Decimal("100")


def test_previous_period_7d(
) -> None:
    start_day = date(
        2026,
        8,
        1,
    )

    rows = make_daily_rows(
        start_day=start_day,
        days=20,
    )

    target_day = (
        start_day
        + timedelta(days=19)
    )

    # Previous period:
    # target -14 through target -8
    for offset in range(
        8,
        15,
    ):
        metric_day = (
            target_day
            - timedelta(days=offset)
        )

        row = next(
            item
            for item in rows
            if item["day"]
            == metric_day.isoformat()
        )

        row["revenue"] = Decimal(
            "50"
        )

    baseline = StorePulseBaselines(
        FakeMetrics(rows)
    )

    result = (
        baseline.order_metric_baseline(
            "revenue",
            as_of_day=target_day,
        )
    )

    assert result[
        "previous_period_7d_avg"
    ] == Decimal("50")


def test_same_weekday_4_week_average(
) -> None:
    start_day = date(
        2026,
        8,
        1,
    )

    rows = make_daily_rows(
        start_day=start_day,
        days=30,
        revenue=Decimal("0"),
    )

    target_day = (
        start_day
        + timedelta(days=29)
    )

    values = [
        Decimal("100"),
        Decimal("200"),
        Decimal("300"),
        Decimal("400"),
    ]

    for week, value in enumerate(
        values,
        start=1,
    ):
        metric_day = (
            target_day
            - timedelta(
                days=week * 7
            )
        )

        row = next(
            item
            for item in rows
            if item["day"]
            == metric_day.isoformat()
        )

        row[
            "revenue"
        ] = value

    baseline = StorePulseBaselines(
        FakeMetrics(rows)
    )

    result = (
        baseline.order_metric_baseline(
            "revenue",
            as_of_day=target_day,
        )
    )

    assert result[
        "same_weekday_4w_avg"
    ] == Decimal("250")


def test_missing_calendar_day_is_zero(
) -> None:
    start_day = date(
        2026,
        8,
        1,
    )

    rows = make_daily_rows(
        start_day=start_day,
        days=8,
        revenue=Decimal("10"),
    )

    target_day = (
        start_day
        + timedelta(days=7)
    )

    # Remove one historical calendar day.
    missing_day = (
        target_day
        - timedelta(days=3)
    )

    rows = [
        row
        for row in rows
        if row["day"]
        != missing_day.isoformat()
    ]

    baseline = StorePulseBaselines(
        FakeMetrics(rows)
    )

    result = (
        baseline.order_metric_baseline(
            "revenue",
            as_of_day=target_day,
        )
    )

    # Six days at 10 + one missing day at 0.
    assert result[
        "avg_7d"
    ] == (
        Decimal("60")
        / Decimal("7")
    )


def test_insufficient_history_returns_none(
) -> None:
    rows = make_daily_rows(
        start_day=date(
            2026,
            8,
            1,
        ),
        days=5,
    )

    baseline = StorePulseBaselines(
        FakeMetrics(rows)
    )

    result = (
        baseline.order_metric_baseline(
            "revenue"
        )
    )

    assert result[
        "avg_7d"
    ] is None

    assert result[
        "avg_14d"
    ] is None

    assert result[
        "avg_28d"
    ] is None

    assert result[
        "previous_period_7d_avg"
    ] is None

    assert result[
        "same_weekday_4w_avg"
    ] is None


def test_all_order_baselines_are_generated(
) -> None:
    rows = make_daily_rows(
        start_day=date(
            2026,
            8,
            1,
        ),
        days=30,
    )

    baseline = StorePulseBaselines(
        FakeMetrics(rows)
    )

    results = baseline.order_baselines()

    assert set(results) == {
        "revenue",
        "orders",
        "aov",
        "units_sold",
    }


def test_as_of_day_after_latest_data_is_rejected(
) -> None:
    rows = make_daily_rows(
        start_day=date(
            2026,
            8,
            1,
        ),
        days=10,
    )

    baseline = StorePulseBaselines(
        FakeMetrics(rows)
    )

    with pytest.raises(
        BaselineError,
        match="later than",
    ):
        baseline.order_metric_baseline(
            "revenue",
            as_of_day=date(
                2026,
                9,
                1,
            ),
        )


def test_empty_history_is_rejected(
) -> None:
    baseline = StorePulseBaselines(
        FakeMetrics([])
    )

    with pytest.raises(
        BaselineError,
        match="No daily",
    ):
        baseline.order_metric_baseline(
            "revenue"
        )


def test_invalid_metric_is_rejected(
) -> None:
    rows = make_daily_rows(
        start_day=date(
            2026,
            8,
            1,
        ),
        days=10,
    )

    baseline = StorePulseBaselines(
        FakeMetrics(rows)
    )

    with pytest.raises(
        ValueError,
        match="Unsupported metric",
    ):
        baseline.order_metric_baseline(
            "something_else"  # type: ignore
        )