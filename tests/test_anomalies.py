from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from analytics.anomalies import (
    AnomalyError,
    StorePulseAnomalyEngine,
)


class FakeBaselines:
    def __init__(
        self,
        *,
        current_value: Decimal,
        avg_7d: Decimal | None,
    ) -> None:
        self.current_value = (
            current_value
        )

        self.avg_7d = avg_7d

    def order_metric_baseline(
        self,
        metric,
        *,
        as_of_day=None,
    ):
        return {
            "metric":
                metric,

            "as_of_day":
                (
                    as_of_day.isoformat()
                    if as_of_day
                    else "2026-09-01"
                ),

            "current_value":
                self.current_value,

            "avg_7d":
                self.avg_7d,

            "avg_14d":
                None,

            "avg_28d":
                None,

            "previous_period_7d_avg":
                None,

            "same_weekday_4w_avg":
                None,

            "history_days":
                28,

            "currency_code":
                "USD",
        }


class MultiMetricBaselines:
    def order_metric_baseline(
        self,
        metric,
        *,
        as_of_day=None,
    ):
        values = {
            "revenue":
                Decimal("100"),

            "orders":
                Decimal("10"),

            "aov":
                Decimal("20"),

            "units_sold":
                Decimal("30"),
        }

        return {
            "metric":
                metric,

            "as_of_day":
                "2026-09-01",

            "current_value":
                values[metric],

            "avg_7d":
                values[metric],

            "avg_14d":
                values[metric],

            "avg_28d":
                values[metric],

            "previous_period_7d_avg":
                values[metric],

            "same_weekday_4w_avg":
                values[metric],

            "history_days":
                30,

            "currency_code":
                "USD",
        }


def test_critical_downside(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "60"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "revenue"
    )

    assert result[
        "severity"
    ] == "CRITICAL"

    assert result[
        "direction"
    ] == "DOWN"

    assert result[
        "deviation_pct"
    ] == Decimal("-40.00")


def test_warning_downside(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "80"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "orders"
    )

    assert result[
        "severity"
    ] == "WARNING"

    assert result[
        "direction"
    ] == "DOWN"

    assert result[
        "deviation_pct"
    ] == Decimal("-20.00")


def test_small_downside_is_normal(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "90"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "revenue"
    )

    assert result[
        "severity"
    ] == "NORMAL"

    assert result[
        "direction"
    ] == "DOWN"

    assert result[
        "deviation_pct"
    ] == Decimal("-10.00")


def test_positive_growth_is_normal(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "130"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "revenue"
    )

    assert result[
        "severity"
    ] == "NORMAL"

    assert result[
        "direction"
    ] == "UP"

    assert result[
        "deviation_pct"
    ] == Decimal("30.00")


def test_exact_warning_boundary(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "85"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "aov"
    )

    assert result[
        "severity"
    ] == "WARNING"


def test_exact_critical_boundary(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "70"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "units_sold"
    )

    assert result[
        "severity"
    ] == "CRITICAL"


def test_insufficient_history(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "100"
            ),
            avg_7d=None,
        )
    )

    result = engine.analyze_order_metric(
        "revenue"
    )

    assert result[
        "severity"
    ] == "INSUFFICIENT_DATA"

    assert result[
        "direction"
    ] == "UNKNOWN"

    assert result[
        "deviation_pct"
    ] is None

    assert result[
        "baseline_value"
    ] is None


def test_zero_current_and_zero_baseline(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "0"
            ),
            avg_7d=Decimal(
                "0"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "orders"
    )

    assert result[
        "severity"
    ] == "NORMAL"

    assert result[
        "direction"
    ] == "FLAT"

    assert result[
        "deviation_pct"
    ] == Decimal("0.00")


def test_positive_value_against_zero_baseline(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "10"
            ),
            avg_7d=Decimal(
                "0"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "orders"
    )

    assert result[
        "severity"
    ] == "NORMAL"

    assert result[
        "direction"
    ] == "UP"

    assert result[
        "deviation_pct"
    ] is None


def test_all_order_metrics_are_analyzed(
) -> None:
    engine = StorePulseAnomalyEngine(
        MultiMetricBaselines()
    )

    results = (
        engine.analyze_order_metrics()
    )

    assert set(results) == {
        "revenue",
        "orders",
        "aov",
        "units_sold",
    }

    for result in results.values():
        assert result[
            "severity"
        ] == "NORMAL"


def test_as_of_day_is_forwarded(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "100"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    result = engine.analyze_order_metric(
        "revenue",
        as_of_day=date(
            2026,
            8,
            31,
        ),
    )

    assert result[
        "as_of_day"
    ] == "2026-08-31"


def test_invalid_thresholds_are_rejected(
) -> None:
    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        StorePulseAnomalyEngine(
            MultiMetricBaselines(),
            warning_threshold_pct=Decimal(
                "0"
            ),
        )

    with pytest.raises(
        ValueError,
        match="greater than",
    ):
        StorePulseAnomalyEngine(
            MultiMetricBaselines(),
            warning_threshold_pct=Decimal(
                "30"
            ),
            critical_threshold_pct=Decimal(
                "20"
            ),
        )


def test_negative_metric_is_rejected(
) -> None:
    engine = StorePulseAnomalyEngine(
        FakeBaselines(
            current_value=Decimal(
                "-10"
            ),
            avg_7d=Decimal(
                "100"
            ),
        )
    )

    with pytest.raises(
        AnomalyError,
        match="cannot be negative",
    ):
        engine.analyze_order_metric(
            "revenue"
        )


def test_invalid_metric_is_rejected(
) -> None:
    engine = StorePulseAnomalyEngine(
        MultiMetricBaselines()
    )

    with pytest.raises(
        ValueError,
        match="Unsupported metric",
    ):
        engine.analyze_order_metric(
            "unknown_metric"  # type: ignore
        )