from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Protocol, TypedDict

from analytics.metrics import DailyOrderMetrics


MetricName = Literal[
    "revenue",
    "orders",
    "aov",
    "units_sold",
]


SUPPORTED_METRICS: tuple[MetricName, ...] = (
    "revenue",
    "orders",
    "aov",
    "units_sold",
)


ZERO = Decimal("0")


class BaselineError(RuntimeError):
    """Raised when a baseline cannot be calculated safely."""


class DailyMetricsProvider(Protocol):
    def daily_order_metrics(
        self,
        *,
        start_at=None,
        end_at=None,
        exclude_cancelled: bool = True,
    ) -> list[DailyOrderMetrics]:
        ...


class BaselineResult(TypedDict):
    metric: MetricName
    as_of_day: str
    current_value: Decimal
    avg_7d: Decimal | None
    avg_14d: Decimal | None
    avg_28d: Decimal | None
    previous_period_7d_avg: Decimal | None
    same_weekday_4w_avg: Decimal | None
    history_days: int
    currency_code: str | None


class StorePulseBaselines:
    """
    Baseline layer for Shopify Store Pulse.

    Reads daily metrics from analytics/metrics.py.

    Does not:
    - Call Shopify
    - Write DuckDB
    - Detect anomalies
    - Assign WARNING / CRITICAL severity

    Baselines always exclude the current day.
    """

    def __init__(
        self,
        metrics: DailyMetricsProvider,
    ) -> None:
        self.metrics = metrics

    def order_metric_baseline(
        self,
        metric: MetricName,
        *,
        as_of_day: date | None = None,
    ) -> BaselineResult:
        """
        Build baselines for one daily order metric.

        Example:

            metric="revenue"

        Baselines:
            avg_7d
                previous 7 calendar days

            avg_14d
                previous 14 calendar days

            avg_28d
                previous 28 calendar days

            previous_period_7d_avg
                days -14 through -8

            same_weekday_4w_avg
                same weekday at:
                -7, -14, -21, -28 days

        Missing calendar days inside the known
        historical range are treated as zero.
        """

        if metric not in SUPPORTED_METRICS:
            raise ValueError(
                f"Unsupported metric: {metric}"
            )

        rows = (
            self.metrics.daily_order_metrics()
        )

        if not rows:
            raise BaselineError(
                "No daily order metrics are available."
            )

        series, currencies = (
            _build_metric_series(
                rows,
                metric,
            )
        )

        earliest_day = min(
            series
        )

        latest_day = max(
            series
        )

        target_day = (
            as_of_day
            if as_of_day is not None
            else latest_day
        )

        if target_day < earliest_day:
            raise BaselineError(
                "as_of_day is earlier than "
                "the available metric history."
            )

        if target_day > latest_day:
            raise BaselineError(
                "as_of_day is later than "
                "the latest available metric day."
            )

        current_value = series.get(
            target_day,
            ZERO,
        )

        history_days = (
            target_day - earliest_day
        ).days

        currency_code = (
            _resolve_currency(
                currencies
            )
        )

        return {
            "metric":
                metric,

            "as_of_day":
                target_day.isoformat(),

            "current_value":
                current_value,

            "avg_7d":
                _rolling_average(
                    series,
                    target_day,
                    days=7,
                    earliest_day=earliest_day,
                ),

            "avg_14d":
                _rolling_average(
                    series,
                    target_day,
                    days=14,
                    earliest_day=earliest_day,
                ),

            "avg_28d":
                _rolling_average(
                    series,
                    target_day,
                    days=28,
                    earliest_day=earliest_day,
                ),

            "previous_period_7d_avg":
                _previous_period_average(
                    series,
                    target_day,
                    period_days=7,
                    earliest_day=earliest_day,
                ),

            "same_weekday_4w_avg":
                _same_weekday_average(
                    series,
                    target_day,
                    weeks=4,
                    earliest_day=earliest_day,
                ),

            "history_days":
                history_days,

            "currency_code":
                currency_code,
        }

    def order_baselines(
        self,
        *,
        as_of_day: date | None = None,
    ) -> dict[MetricName, BaselineResult]:
        """
        Build baseline results for all current
        order-related Store Pulse metrics.
        """

        return {
            metric:
                self.order_metric_baseline(
                    metric,
                    as_of_day=as_of_day,
                )
            for metric in SUPPORTED_METRICS
        }


def _build_metric_series(
    rows: Sequence[DailyOrderMetrics],
    metric: MetricName,
) -> tuple[
    dict[date, Decimal],
    set[str],
]:
    series: dict[
        date,
        Decimal
    ] = {}

    currencies: set[str] = set()

    for row in rows:
        day_text = row.get(
            "day"
        )

        if not isinstance(
            day_text,
            str,
        ):
            raise BaselineError(
                "Daily metric day is invalid."
            )

        try:
            metric_day = date.fromisoformat(
                day_text
            )

        except ValueError as exc:
            raise BaselineError(
                f"Invalid daily metric date: "
                f"{day_text}"
            ) from exc

        if metric_day in series:
            raise BaselineError(
                "Duplicate daily metric row "
                f"for {day_text}."
            )

        raw_value = row.get(
            metric
        )

        series[
            metric_day
        ] = _to_decimal(
            raw_value,
            metric,
        )

        currency_code = row.get(
            "currency_code"
        )

        if currency_code is not None:
            if not isinstance(
                currency_code,
                str,
            ):
                raise BaselineError(
                    "Daily metric currency "
                    "is invalid."
                )

            currencies.add(
                currency_code
            )

    return (
        series,
        currencies,
    )


def _rolling_average(
    series: dict[date, Decimal],
    target_day: date,
    *,
    days: int,
    earliest_day: date,
) -> Decimal | None:
    """
    Average the calendar days immediately before
    target_day.

    target_day itself is deliberately excluded.
    """

    required_start = (
        target_day
        - timedelta(days=days)
    )

    if required_start < earliest_day:
        return None

    total = ZERO

    for offset in range(
        1,
        days + 1,
    ):
        metric_day = (
            target_day
            - timedelta(days=offset)
        )

        total += series.get(
            metric_day,
            ZERO,
        )

    return (
        total
        / Decimal(days)
    )


def _previous_period_average(
    series: dict[date, Decimal],
    target_day: date,
    *,
    period_days: int,
    earliest_day: date,
) -> Decimal | None:
    """
    Previous period before the most recent window.

    For period_days=7:

        current baseline window:
            day -7 through day -1

        previous period:
            day -14 through day -8
    """

    required_start = (
        target_day
        - timedelta(
            days=period_days * 2
        )
    )

    if required_start < earliest_day:
        return None

    total = ZERO

    start_offset = (
        period_days + 1
    )

    end_offset = (
        period_days * 2
    )

    for offset in range(
        start_offset,
        end_offset + 1,
    ):
        metric_day = (
            target_day
            - timedelta(days=offset)
        )

        total += series.get(
            metric_day,
            ZERO,
        )

    return (
        total
        / Decimal(period_days)
    )


def _same_weekday_average(
    series: dict[date, Decimal],
    target_day: date,
    *,
    weeks: int,
    earliest_day: date,
) -> Decimal | None:
    """
    Average the same weekday from previous weeks.

    Example for Tuesday:
        previous Tuesday
        Tuesday -2 weeks
        Tuesday -3 weeks
        Tuesday -4 weeks
    """

    oldest_day = (
        target_day
        - timedelta(
            days=weeks * 7
        )
    )

    if oldest_day < earliest_day:
        return None

    total = ZERO

    for week in range(
        1,
        weeks + 1,
    ):
        metric_day = (
            target_day
            - timedelta(
                days=week * 7
            )
        )

        total += series.get(
            metric_day,
            ZERO,
        )

    return (
        total
        / Decimal(weeks)
    )


def _resolve_currency(
    currencies: set[str],
) -> str | None:
    if not currencies:
        return None

    if len(currencies) > 1:
        raise BaselineError(
            "Multiple currencies detected "
            "in daily metric history: "
            + ", ".join(
                sorted(currencies)
            )
        )

    return next(
        iter(currencies)
    )


def _to_decimal(
    value,
    metric: MetricName,
) -> Decimal:
    if isinstance(
        value,
        bool,
    ):
        raise BaselineError(
            f"Invalid value for {metric}."
        )

    try:
        return Decimal(
            str(value)
        )

    except Exception as exc:
        raise BaselineError(
            f"Invalid value for "
            f"{metric}: {value}"
        ) from exc