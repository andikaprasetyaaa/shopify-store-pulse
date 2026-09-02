from __future__ import annotations

"""
Forecast payload for the dashboard chart.

Reads the daily history, produces the forward
prediction with its band, and hands back a single
series the chart can draw end to end.
"""

from datetime import date
from typing import Any

import duckdb

from analytics.forecast import (
    BENCHMARK,
    ForecastError,
    Point,
    backtest,
    forecast,
    summarize,
)
from api.deps import (
    database_path,
    require_database,
)

DEFAULT_MODEL = "damped_trend"

# Backtesting on this store shows the model beating
# the benchmark up to roughly h+11 and drawing level
# after that, so offering more than two weeks would
# be selling certainty that is not there.
MAX_HORIZON = 14


def load_history(
    metric: str = "orders",
) -> list[Point]:
    """
    Daily history up to yesterday.

    Today is excluded because it is still collecting
    orders. Feeding a half finished day to the model
    would read as a sudden collapse in demand.
    """

    column = (
        "COUNT(*)"
        if metric == "orders"
        else "SUM(total_price)"
    )

    connection = duckdb.connect(
        str(database_path()),
        read_only=True,
    )

    try:
        rows = connection.execute(
            f"""
            SELECT
                created_at::DATE AS day,
                {column} AS value
            FROM orders
            WHERE cancelled_at IS NULL
              AND created_at::DATE < CURRENT_DATE
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchall()

    finally:
        connection.close()

    return [
        Point(
            day=row[0],
            value=float(row[1]),
        )
        for row in rows
    ]


def build_forecast(
    metric: str = "orders",
    horizon: int = 7,
    history_days: int = 30,
) -> dict[str, Any]:
    require_database()

    points = load_history(metric)

    if not points:
        return {
            "metric": metric,
            "model": None,
            "history": [],
            "forecast": [],
            "accuracy": None,
            "error": (
                "No order history available."
            ),
        }

    horizon = max(
        1,
        min(horizon, MAX_HORIZON),
    )

    try:
        predictions = forecast(
            points,
            horizon=horizon,
            model_name=DEFAULT_MODEL,
        )

        accuracy = accuracy_summary(
            [
                point.value
                for point in points
            ],
            horizon,
        )

        error = None

    except ForecastError as exc:
        predictions = []
        accuracy = None
        error = str(exc)

    return {
        "metric": metric,
        "model": DEFAULT_MODEL,
        "history": [
            {
                "day": point.day.isoformat(),
                "value": point.value,
            }
            for point in points[-history_days:]
        ],
        "forecast": [
            {
                "day":
                    prediction.day.isoformat(),

                "predicted":
                    prediction.predicted,

                "lower":
                    prediction.lower,

                "upper":
                    prediction.upper,
            }
            for prediction in predictions
        ],
        "accuracy": accuracy,
        "error": error,
    }


def accuracy_summary(
    values: list[float],
    horizon: int,
) -> dict[str, Any] | None:
    """
    How the deployed model scored against the
    benchmark, so the number on screen carries its
    own track record.
    """

    try:
        scores = backtest(
            values,
            horizon=horizon,
        )

    except ForecastError:
        return None

    ranking = summarize(scores)

    return {
        "model_mape": round(
            ranking[DEFAULT_MODEL],
            1,
        ),
        "benchmark": BENCHMARK,
        "benchmark_mape": round(
            ranking[BENCHMARK],
            1,
        ),
        "folds": scores[0].folds,
    }
