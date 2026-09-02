from __future__ import annotations

import sys
from decimal import Decimal

from analytics.anomalies import (
    AnomalyError,
    AnomalyResult,
    StorePulseAnomalyEngine,
)
from analytics.baseline import (
    BaselineError,
    StorePulseBaselines,
)
from analytics.metrics import (
    MetricsError,
    StorePulseMetrics,
)


def format_value(
    value: Decimal | None,
) -> str:
    if value is None:
        return "N/A"

    return f"{value:.2f}"


def print_anomaly(
    result: AnomalyResult,
) -> None:
    metric = result[
        "metric"
    ]

    currency = result[
        "currency_code"
    ]

    suffix = ""

    if (
        metric in {
            "revenue",
            "aov",
        }
        and currency
    ):
        suffix = (
            f" {currency}"
        )

    current = format_value(
        result[
            "current_value"
        ]
    )

    baseline = format_value(
        result[
            "baseline_value"
        ]
    )

    deviation = (
        format_value(
            result[
                "deviation_pct"
            ]
        )
    )

    print()
    print(
        f"{metric}:"
    )

    print(
        "  As of: "
        f"{result['as_of_day']}"
    )

    print(
        "  Current: "
        f"{current}{suffix}"
    )

    print(
        "  Baseline: "
        f"{baseline}{suffix}"
    )

    if (
        result[
            "deviation_pct"
        ]
        is None
    ):
        print(
            "  Deviation: N/A"
        )

    else:
        print(
            "  Deviation: "
            f"{deviation}%"
        )

    print(
        "  Direction: "
        f"{result['direction']}"
    )

    print(
        "  Severity: "
        f"{result['severity']}"
    )

    print(
        "  Reason: "
        f"{result['reason']}"
    )


def main() -> int:
    print(
        "Shopify Store Pulse - Anomaly Check"
    )

    try:
        with StorePulseMetrics() as metrics:
            baseline_engine = (
                StorePulseBaselines(
                    metrics
                )
            )

            anomaly_engine = (
                StorePulseAnomalyEngine(
                    baseline_engine
                )
            )

            results = (
                anomaly_engine
                .analyze_order_metrics()
            )

    except (
        MetricsError,
        BaselineError,
        AnomalyError,
        ValueError,
    ) as exc:
        print(
            "[FAIL] Anomaly check failed: "
            f"{exc}",
            file=sys.stderr,
        )

        print(
            "[INFO] Run database, metrics, "
            "and baseline checks first."
        )

        return 1

    for metric in (
        "revenue",
        "orders",
        "aov",
        "units_sold",
    ):
        print_anomaly(
            results[
                metric
            ]
        )

    warning_metrics = [
        metric
        for metric, result
        in results.items()
        if result[
            "severity"
        ] == "WARNING"
    ]

    critical_metrics = [
        metric
        for metric, result
        in results.items()
        if result[
            "severity"
        ] == "CRITICAL"
    ]

    insufficient_metrics = [
        metric
        for metric, result
        in results.items()
        if result[
            "severity"
        ] == "INSUFFICIENT_DATA"
    ]

    print()
    print("Anomaly summary:")

    print(
        "  Critical: "
        f"{len(critical_metrics)}"
    )

    print(
        "  Warning: "
        f"{len(warning_metrics)}"
    )

    print(
        "  Insufficient data: "
        f"{len(insufficient_metrics)}"
    )

    if critical_metrics:
        print(
            "  Critical metrics: "
            + ", ".join(
                critical_metrics
            )
        )

    if warning_metrics:
        print(
            "  Warning metrics: "
            + ", ".join(
                warning_metrics
            )
        )

    if insufficient_metrics:
        print(
            "  Waiting for history: "
            + ", ".join(
                insufficient_metrics
            )
        )

    print()

    print(
        "[PASS] Anomaly engine smoke test completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )