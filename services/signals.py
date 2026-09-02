from __future__ import annotations

"""
Anomaly signals built on top of the baseline engine.
"""

from typing import Any

from analytics.anomalies import (
    AnomalyError,
    StorePulseAnomalyEngine,
)
from analytics.baseline import (
    BaselineError,
    StorePulseBaselines,
)
from analytics.metrics import (
    StorePulseMetrics,
)
from api.deps import (
    database_path,
    require_database,
)
from api.formatting import (
    serialize_anomaly,
)


def load_signals(
    metrics: StorePulseMetrics,
) -> tuple[
    dict[str, Any],
    str | None,
]:
    try:
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

        return (
            {
                metric:
                    serialize_anomaly(
                        result
                    )
                for (
                    metric,
                    result,
                ) in results.items()
            },
            None,
        )

    except (
        BaselineError,
        AnomalyError,
        ValueError,
    ) as exc:
        return (
            {},
            str(exc),
        )


def build_signals() -> dict[str, Any]:
    require_database()

    with StorePulseMetrics(
        database_path()
    ) as metrics:
        results, error = (
            load_signals(
                metrics
            )
        )

    return {
        "signals":
            results,

        "error":
            error,
    }
