from __future__ import annotations

"""
Backtest the forecast models against real history.

    python -m scripts.check_forecast
    python -m scripts.check_forecast --metric revenue
"""

import argparse
import sys
from datetime import date, timedelta

import duckdb

from analytics.forecast import (
    BENCHMARK,
    ForecastError,
    Point,
    backtest,
    forecast,
    summarize,
)
from api.deps import database_path


def load_series(
    metric: str,
) -> list[Point]:
    """
    Daily history, excluding today.

    Today is still accumulating orders, so including
    it would teach every model that the latest day is
    unusually quiet.
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


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--metric",
        choices=["orders", "revenue"],
        default="orders",
    )

    parser.add_argument(
        "--horizon",
        type=int,
        default=14,
    )

    args = parser.parse_args()

    points = load_series(args.metric)

    print(
        f"Metric        : {args.metric}"
    )

    print(
        f"History       : {len(points)} days "
        f"({points[0].day} -> {points[-1].day})"
    )

    values = [
        point.value for point in points
    ]

    try:
        scores = backtest(
            values,
            horizon=args.horizon,
        )

    except ForecastError as exc:
        print(
            f"[FAIL] {exc}",
            file=sys.stderr,
        )
        return 1

    ranking = summarize(scores)

    benchmark = ranking[BENCHMARK]

    print()
    print(
        "Rolling origin backtest "
        f"(horizon {args.horizon}, "
        f"{scores[0].folds} folds at h+1)"
    )
    print()

    print(
        f"  {'model':<18}"
        f"{'MAPE':>8}"
        f"{'vs benchmark':>15}"
    )

    print("  " + "-" * 41)

    for name, mape in sorted(
        ranking.items(),
        key=lambda item: item[1],
    ):
        delta = (
            (mape - benchmark)
            / benchmark
            * 100.0
        )

        verdict = (
            "  <- benchmark"
            if name == BENCHMARK
            else f"{delta:+.1f}%"
        )

        print(
            f"  {name:<18}"
            f"{mape:>7.1f}%"
            f"{verdict:>15}"
        )

    winner = min(
        ranking,
        key=ranking.get,
    )

    print()
    print(
        "MAPE by horizon "
        f"({winner} vs {BENCHMARK}):"
    )
    print()

    print(
        f"  {'h':>3}"
        f"{winner:>18}"
        f"{BENCHMARK:>18}"
    )

    print("  " + "-" * 39)

    by_horizon = {
        (score.model, score.horizon): score
        for score in scores
    }

    for step in range(
        1,
        args.horizon + 1,
    ):
        best = by_horizon[(winner, step)]
        base = by_horizon[(BENCHMARK, step)]

        print(
            f"  {step:>3}"
            f"{best.mape:>17.1f}%"
            f"{base.mape:>17.1f}%"
        )

    print()

    if winner == BENCHMARK:
        print(
            "[RESULT] Nothing beats the seasonal "
            "naive benchmark. Ship the benchmark."
        )

    else:
        improvement = (
            (benchmark - ranking[winner])
            / benchmark
            * 100.0
        )

        print(
            f"[RESULT] '{winner}' beats the "
            f"benchmark by {improvement:.1f}% "
            "MAPE."
        )

    print()
    print(
        f"Next {args.horizon} days "
        f"using '{winner}':"
    )
    print()

    for prediction in forecast(
        points,
        horizon=args.horizon,
        model_name=winner,
    ):
        print(
            f"  {prediction.day}  "
            f"{prediction.predicted:>10,.0f}   "
            f"[{prediction.lower:>10,.0f} .. "
            f"{prediction.upper:>10,.0f}]"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
