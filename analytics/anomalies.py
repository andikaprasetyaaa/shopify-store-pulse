from __future__ import annotations

from datetime import date
from decimal import (
    Decimal,
    ROUND_HALF_UP,
)
from typing import (
    Literal,
    Protocol,
    TypedDict,
)

from analytics.baseline import (
    BaselineResult,
    MetricName,
    SUPPORTED_METRICS,
)


Severity = Literal[
    "NORMAL",
    "WARNING",
    "CRITICAL",
    "INSUFFICIENT_DATA",
]

Direction = Literal[
    "UP",
    "DOWN",
    "FLAT",
    "UNKNOWN",
]


DEFAULT_WARNING_THRESHOLD = Decimal("15")
DEFAULT_CRITICAL_THRESHOLD = Decimal("30")

PERCENT_QUANTIZER = Decimal("0.01")


class AnomalyError(RuntimeError):
    """Raised when anomaly analysis cannot be performed safely."""


class BaselineProvider(Protocol):
    def order_metric_baseline(
        self,
        metric: MetricName,
        *,
        as_of_day: date | None = None,
    ) -> BaselineResult:
        ...


class AnomalyResult(TypedDict):
    metric: MetricName
    as_of_day: str

    current_value: Decimal

    baseline_name: str
    baseline_value: Decimal | None

    deviation_pct: Decimal | None

    direction: Direction
    severity: Severity

    warning_threshold_pct: Decimal
    critical_threshold_pct: Decimal

    history_days: int
    currency_code: str | None

    reason: str


class StorePulseAnomalyEngine:
    """
    Deterministic anomaly engine for Shopify Store Pulse.

    MVP behavior:
    - Uses avg_7d as the primary baseline
    - Detects downside anomalies
    - Positive growth is not treated as an alert
    - Does not call Shopify
    - Does not write DuckDB
    - Does not send notifications
    """

    def __init__(
        self,
        baselines: BaselineProvider,
        *,
        warning_threshold_pct: Decimal = (
            DEFAULT_WARNING_THRESHOLD
        ),
        critical_threshold_pct: Decimal = (
            DEFAULT_CRITICAL_THRESHOLD
        ),
    ) -> None:
        warning = _to_decimal(
            warning_threshold_pct,
            "warning_threshold_pct",
        )

        critical = _to_decimal(
            critical_threshold_pct,
            "critical_threshold_pct",
        )

        if warning <= 0:
            raise ValueError(
                "warning_threshold_pct must "
                "be greater than zero."
            )

        if critical <= warning:
            raise ValueError(
                "critical_threshold_pct must "
                "be greater than "
                "warning_threshold_pct."
            )

        self.baselines = baselines

        self.warning_threshold_pct = (
            warning
        )

        self.critical_threshold_pct = (
            critical
        )

    def analyze_order_metric(
        self,
        metric: MetricName,
        *,
        as_of_day: date | None = None,
    ) -> AnomalyResult:
        """
        Analyze one order metric against its
        previous 7-day average.

        Severity rules:

        NORMAL
            downside < warning threshold

        WARNING
            downside >= warning threshold

        CRITICAL
            downside >= critical threshold

        INSUFFICIENT_DATA
            7-day baseline is unavailable
        """

        if metric not in SUPPORTED_METRICS:
            raise ValueError(
                f"Unsupported metric: {metric}"
            )

        baseline = (
            self.baselines.order_metric_baseline(
                metric,
                as_of_day=as_of_day,
            )
        )

        current_value = _to_decimal(
            baseline["current_value"],
            "current_value",
        )

        if current_value < 0:
            raise AnomalyError(
                f"{metric} current value "
                "cannot be negative."
            )

        baseline_value = baseline[
            "avg_7d"
        ]

        if baseline_value is None:
            return {
                "metric":
                    metric,

                "as_of_day":
                    baseline["as_of_day"],

                "current_value":
                    current_value,

                "baseline_name":
                    "avg_7d",

                "baseline_value":
                    None,

                "deviation_pct":
                    None,

                "direction":
                    "UNKNOWN",

                "severity":
                    "INSUFFICIENT_DATA",

                "warning_threshold_pct":
                    self.warning_threshold_pct,

                "critical_threshold_pct":
                    self.critical_threshold_pct,

                "history_days":
                    baseline["history_days"],

                "currency_code":
                    baseline["currency_code"],

                "reason":
                    (
                        "7-day baseline is unavailable; "
                        "at least 7 prior calendar days "
                        "are required."
                    ),
            }

        baseline_decimal = _to_decimal(
            baseline_value,
            "avg_7d",
        )

        if baseline_decimal < 0:
            raise AnomalyError(
                f"{metric} baseline value "
                "cannot be negative."
            )

        return self._evaluate(
            metric=metric,
            baseline=baseline,
            current_value=current_value,
            baseline_value=baseline_decimal,
        )

    def analyze_order_metrics(
        self,
        *,
        as_of_day: date | None = None,
    ) -> dict[
        MetricName,
        AnomalyResult,
    ]:
        """
        Analyze all current order metrics.
        """

        return {
            metric:
                self.analyze_order_metric(
                    metric,
                    as_of_day=as_of_day,
                )
            for metric in SUPPORTED_METRICS
        }

    def _evaluate(
        self,
        *,
        metric: MetricName,
        baseline: BaselineResult,
        current_value: Decimal,
        baseline_value: Decimal,
    ) -> AnomalyResult:
        if baseline_value == 0:
            return self._evaluate_zero_baseline(
                metric=metric,
                baseline=baseline,
                current_value=current_value,
            )

        deviation_pct = (
            (
                current_value
                - baseline_value
            )
            / baseline_value
            * Decimal("100")
        ).quantize(
            PERCENT_QUANTIZER,
            rounding=ROUND_HALF_UP,
        )

        if deviation_pct > 0:
            direction: Direction = "UP"

        elif deviation_pct < 0:
            direction = "DOWN"

        else:
            direction = "FLAT"

        severity: Severity = "NORMAL"

        if direction == "DOWN":
            downside_pct = abs(
                deviation_pct
            )

            if (
                downside_pct
                >= self.critical_threshold_pct
            ):
                severity = "CRITICAL"

            elif (
                downside_pct
                >= self.warning_threshold_pct
            ):
                severity = "WARNING"

        reason = _build_reason(
            metric=metric,
            direction=direction,
            severity=severity,
            deviation_pct=deviation_pct,
        )

        return {
            "metric":
                metric,

            "as_of_day":
                baseline["as_of_day"],

            "current_value":
                current_value,

            "baseline_name":
                "avg_7d",

            "baseline_value":
                baseline_value,

            "deviation_pct":
                deviation_pct,

            "direction":
                direction,

            "severity":
                severity,

            "warning_threshold_pct":
                self.warning_threshold_pct,

            "critical_threshold_pct":
                self.critical_threshold_pct,

            "history_days":
                baseline["history_days"],

            "currency_code":
                baseline["currency_code"],

            "reason":
                reason,
        }

    def _evaluate_zero_baseline(
        self,
        *,
        metric: MetricName,
        baseline: BaselineResult,
        current_value: Decimal,
    ) -> AnomalyResult:
        if current_value == 0:
            direction: Direction = "FLAT"

            deviation_pct: Decimal | None = (
                Decimal("0.00")
            )

            reason = (
                f"{metric} and its 7-day baseline "
                "are both zero."
            )

        else:
            direction = "UP"
            deviation_pct = None

            reason = (
                f"{metric} is above a zero "
                "7-day baseline. Percentage "
                "deviation is not meaningful."
            )

        return {
            "metric":
                metric,

            "as_of_day":
                baseline["as_of_day"],

            "current_value":
                current_value,

            "baseline_name":
                "avg_7d",

            "baseline_value":
                Decimal("0"),

            "deviation_pct":
                deviation_pct,

            "direction":
                direction,

            "severity":
                "NORMAL",

            "warning_threshold_pct":
                self.warning_threshold_pct,

            "critical_threshold_pct":
                self.critical_threshold_pct,

            "history_days":
                baseline["history_days"],

            "currency_code":
                baseline["currency_code"],

            "reason":
                reason,
        }


def _build_reason(
    *,
    metric: MetricName,
    direction: Direction,
    severity: Severity,
    deviation_pct: Decimal,
) -> str:
    magnitude = abs(
        deviation_pct
    )

    if direction == "DOWN":
        if severity == "CRITICAL":
            return (
                f"{metric} is {magnitude:.2f}% below "
                "the 7-day baseline and exceeds "
                "the critical downside threshold."
            )

        if severity == "WARNING":
            return (
                f"{metric} is {magnitude:.2f}% below "
                "the 7-day baseline and exceeds "
                "the warning downside threshold."
            )

        return (
            f"{metric} is {magnitude:.2f}% below "
            "the 7-day baseline but remains "
            "within the normal range."
        )

    if direction == "UP":
        return (
            f"{metric} is {magnitude:.2f}% above "
            "the 7-day baseline. "
            "No downside alert."
        )

    return (
        f"{metric} matches the 7-day baseline."
    )


def _to_decimal(
    value,
    field_name: str,
) -> Decimal:
    if isinstance(
        value,
        bool,
    ):
        raise AnomalyError(
            f"{field_name} is invalid."
        )

    try:
        return Decimal(
            str(value)
        )

    except Exception as exc:
        raise AnomalyError(
            f"{field_name} is invalid: "
            f"{value}"
        ) from exc