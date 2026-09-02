from __future__ import annotations

import sys
from decimal import Decimal

from analytics.baseline import (
    BaselineError,
    BaselineResult,
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


def print_baseline(
    result: BaselineResult,
) -> None:
    metric = result["metric"]
    currency = result["currency_code"]

    suffix = ""

    if (
        metric in {
            "revenue",
            "aov",
        }
        and currency
    ):
        suffix = f" {currency}"

    current_value = format_value(
        result["current_value"]
    )

    avg_7d = format_value(
        result["avg_7d"]
    )

    avg_14d = format_value(
        result["avg_14d"]
    )

    avg_28d = format_value(
        result["avg_28d"]
    )

    previous_7d = format_value(
        result[
            "previous_period_7d_avg"
        ]
    )

    same_weekday = format_value(
        result[
            "same_weekday_4w_avg"
        ]
    )

    print()
    print(f"{metric}:")

    print(
        "  As of: "
        f"{result['as_of_day']}"
    )

    print(
        "  Current: "
        f"{current_value}{suffix}"
    )

    print(
        "  7-day avg: "
        f"{avg_7d}{suffix}"
    )

    print(
        "  14-day avg: "
        f"{avg_14d}{suffix}"
    )

    print(
        "  28-day avg: "
        f"{avg_28d}{suffix}"
    )

    print(
        "  Previous 7-day period avg: "
        f"{previous_7d}{suffix}"
    )

    print(
        "  Same weekday 4-week avg: "
        f"{same_weekday}{suffix}"
    )

    print(
        "  History days: "
        f"{result['history_days']}"
    )


def main() -> int:
    print(
        "Shopify Store Pulse - Baseline Check"
    )

    try:
        with StorePulseMetrics() as metrics:
            baseline_engine = (
                StorePulseBaselines(
                    metrics
                )
            )

            baselines = (
                baseline_engine.order_baselines()
            )

    except (
        MetricsError,
        BaselineError,
    ) as exc:
        print(
            "[FAIL] Baseline check failed: "
            f"{exc}",
            file=sys.stderr,
        )

        print(
            "[INFO] Run database and metrics "
            "checks first."
        )

        return 1

    for metric in (
        "revenue",
        "orders",
        "aov",
        "units_sold",
    ):
        print_baseline(
            baselines[metric]
        )

    unavailable_28d = [
        metric
        for metric, result in baselines.items()
        if result["avg_28d"] is None
    ]

    print()

    if unavailable_28d:
        print(
            "[INFO] 28-day baseline not yet "
            "available for: "
            + ", ".join(
                unavailable_28d
            )
        )

        print(
            "[INFO] More historical daily "
            "data is required."
        )

    else:
        print(
            "[OK] 28-day baselines available "
            "for all order metrics"
        )

    print(
        "[PASS] Baseline smoke test completed"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )