from __future__ import annotations

"""
Short-horizon forecasting for daily store metrics.

Deliberately simple. The store has roughly 60 days of
order history because the `read_orders` scope only
exposes a 60 day window, which rules out yearly
seasonality, holiday effects and anything that needs
year-over-year context. What it does support is a
weekly cycle plus a level, and that is what these
models capture.

Every model here is a plain function of the history,
with no fitted state to persist and no third party
dependency. `backtest()` scores them by rolling
origin so a candidate has to earn its place against
the seasonal naive benchmark.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Sequence

WEEK = 7


class ForecastError(RuntimeError):
    """Raised when a forecast cannot be produced."""


@dataclass(frozen=True)
class Point:
    """One day of history."""

    day: date
    value: float


@dataclass(frozen=True)
class Prediction:
    """One forecast day with an uncertainty band."""

    day: date
    predicted: float
    lower: float
    upper: float


# ============================================================
# Models
# ============================================================
#
# Each model takes the history and a horizon, and
# returns `horizon` predicted values. They never see
# the future: callers slice the history first.


def naive(
    history: Sequence[float],
    horizon: int,
) -> list[float]:
    """Tomorrow looks like today."""

    return [history[-1]] * horizon


def mean_7(
    history: Sequence[float],
    horizon: int,
) -> list[float]:
    """Flat average of the trailing week."""

    window = history[-WEEK:]

    average = sum(window) / len(window)

    return [average] * horizon


def seasonal_naive(
    history: Sequence[float],
    horizon: int,
) -> list[float]:
    """
    The benchmark: each day looks like the same
    weekday last week.

    Any model that cannot beat this is not worth
    deploying.
    """

    if len(history) < WEEK:
        return naive(history, horizon)

    return [
        history[-WEEK + (step % WEEK)]
        for step in range(horizon)
    ]


def weekday_profile(
    history: Sequence[float],
    horizon: int,
    *,
    level_days: int = WEEK,
) -> list[float]:
    """
    Level times weekday factor.

    The level is the trailing mean, and each weekday
    carries a multiplicative factor measured over as
    many whole weeks as the history allows. This is
    steadier than seasonal naive because one unusual
    day moves a weekday factor only slightly instead
    of becoming next week's entire forecast.

    `level_days` defaults to exactly one week for a
    reason worth keeping. A whole number of weeks
    contains each weekday once, so the mean carries
    no weekday bias, and the shortest such window
    tracks a changing level fastest. On this store
    that matters: backtesting a 28 day level scored
    24.3% MAPE against 17.9% for a 7 day level,
    because the longer window lagged behind real
    growth. The weekday factors still use eight weeks
    since a shape needs more data than a level.
    """

    if len(history) < 2 * WEEK:
        return seasonal_naive(history, horizon)

    window = history[-level_days:]

    level = sum(window) / len(window)

    if level == 0:
        return [0.0] * horizon

    factors = weekday_factors(history)

    # history[-1] is the most recent day, so the day
    # `step` days ahead sits at this offset.
    return [
        level
        * factors[
            (len(history) + step) % WEEK
        ]
        for step in range(horizon)
    ]


def weekday_factors(
    history: Sequence[float],
    *,
    weeks: int = 8,
) -> list[float]:
    """
    Average value per weekday slot, divided by the
    overall average.

    Slot `i` holds the days at position i modulo 7
    counting from the start of the trailing window,
    which keeps the caller free of calendar handling.
    """

    window = list(history[-weeks * WEEK:])

    overall = sum(window) / len(window)

    if overall == 0:
        return [1.0] * WEEK

    factors: list[float] = []

    offset = len(history) - len(window)

    for slot in range(WEEK):
        values = [
            value
            for index, value in enumerate(window)
            if (offset + index) % WEEK == slot
        ]

        factors.append(
            (sum(values) / len(values)) / overall
            if values
            else 1.0
        )

    return factors


def damped_trend(
    history: Sequence[float],
    horizon: int,
    *,
    damping: float = 0.85,
    level_days: int = WEEK,
) -> list[float]:
    """
    Weekday profile plus a damped linear trend.

    A raw trend extrapolated from 60 days of a
    growing store runs away quickly, so each step
    ahead keeps only `damping` of the previous step's
    increment. The trend contributes early and fades.
    """

    base = weekday_profile(
        history,
        horizon,
        level_days=level_days,
    )

    if len(history) < 2 * WEEK:
        return base

    # Slope between the two most recent whole weeks,
    # per day.
    recent = history[-WEEK:]
    previous = history[-2 * WEEK:-WEEK]

    slope = (
        sum(recent) / len(recent)
        - sum(previous) / len(previous)
    ) / WEEK

    predictions: list[float] = []

    increment = 0.0

    for step, value in enumerate(base):
        increment = (
            increment * damping
            + slope * (damping ** step)
        )

        predictions.append(
            max(0.0, value + increment)
        )

    return predictions


Model = Callable[
    [Sequence[float], int],
    list[float],
]


MODELS: dict[str, Model] = {
    "naive": naive,
    "mean_7": mean_7,
    "seasonal_naive": seasonal_naive,
    "weekday_profile": weekday_profile,
    "damped_trend": damped_trend,
}


BENCHMARK = "seasonal_naive"


# ============================================================
# Backtesting
# ============================================================


@dataclass(frozen=True)
class Score:
    """Accuracy of one model at one horizon."""

    model: str
    horizon: int
    mae: float
    mape: float
    folds: int


def backtest(
    history: Sequence[float],
    *,
    horizon: int = 14,
    min_train: int = 28,
    models: dict[str, Model] | None = None,
) -> list[Score]:
    """
    Rolling origin evaluation.

    A single train/test split would leave about ten
    test days here, few enough that one campaign day
    decides the winner. Instead the origin walks
    forward one day at a time: train on days up to t,
    predict the next `horizon` days, score, advance.
    That yields tens of evaluations from the same
    short history, and separates accuracy at h+1 from
    accuracy at h+14.

    Nothing at or after the cutoff is visible to the
    model, so there is no leakage.
    """

    values = list(history)

    if len(values) < min_train + 1:
        raise ForecastError(
            "Not enough history to backtest. "
            f"Need {min_train + 1} days, "
            f"got {len(values)}."
        )

    candidates = models or MODELS

    errors: dict[
        tuple[str, int],
        list[tuple[float, float]],
    ] = {}

    for cutoff in range(
        min_train,
        len(values),
    ):
        train = values[:cutoff]

        actual = values[
            cutoff : cutoff + horizon
        ]

        if not actual:
            break

        for name, model in candidates.items():
            predicted = model(
                train,
                len(actual),
            )

            for step, (
                forecast_value,
                actual_value,
            ) in enumerate(
                zip(predicted, actual),
                start=1,
            ):
                absolute = abs(
                    forecast_value - actual_value
                )

                relative = (
                    absolute / actual_value
                    if actual_value
                    else 0.0
                )

                errors.setdefault(
                    (name, step),
                    [],
                ).append(
                    (absolute, relative)
                )

    scores: list[Score] = []

    for (name, step), pairs in sorted(
        errors.items()
    ):
        scores.append(
            Score(
                model=name,
                horizon=step,
                mae=sum(
                    absolute
                    for absolute, _ in pairs
                )
                / len(pairs),
                mape=100.0
                * sum(
                    relative
                    for _, relative in pairs
                )
                / len(pairs),
                folds=len(pairs),
            )
        )

    return scores


def summarize(
    scores: Sequence[Score],
) -> dict[str, float]:
    """
    Mean MAPE per model across every horizon, which
    is how the models are ranked.
    """

    totals: dict[str, list[float]] = {}

    for score in scores:
        totals.setdefault(
            score.model,
            [],
        ).append(score.mape)

    return {
        name: sum(values) / len(values)
        for name, values in totals.items()
    }


# ============================================================
# Forecasting with an uncertainty band
# ============================================================


def residual_spread(
    history: Sequence[float],
    model: Model,
    *,
    horizon: int,
    min_train: int = 28,
) -> dict[int, float]:
    """
    Mean absolute error per horizon, measured by
    backtest and reused as the band width.

    The band widens with the horizon because that is
    what the backtest actually shows. With this much
    history the band is wide, and hiding it would
    make the forecast look more certain than it is.
    """

    scores = backtest(
        history,
        horizon=horizon,
        min_train=min_train,
        models={"model": model},
    )

    return {
        score.horizon: score.mae
        for score in scores
    }


def forecast(
    points: Sequence[Point],
    *,
    horizon: int = 14,
    model_name: str = "weekday_profile",
    band_multiplier: float = 1.28,
    min_train: int = 28,
) -> list[Prediction]:
    """
    Produce `horizon` days of forecast after the last
    day in `points`.

    `band_multiplier` scales the backtested mean
    absolute error into the band. 1.28 is the normal
    distribution's 80% two-sided quantile, so the
    band reads as "we expect the actual to land in
    here about 80% of the time" rather than as a
    guarantee.
    """

    if not points:
        raise ForecastError(
            "Cannot forecast without history."
        )

    model = MODELS.get(model_name)

    if model is None:
        raise ForecastError(
            f"Unknown model '{model_name}'."
        )

    ordered = sorted(
        points,
        key=lambda point: point.day,
    )

    values = [
        point.value for point in ordered
    ]

    predicted = model(values, horizon)

    try:
        spread = residual_spread(
            values,
            model,
            horizon=horizon,
            min_train=min_train,
        )

    except ForecastError:
        # Too little history to measure a band.
        spread = {}

    last_day = ordered[-1].day

    predictions: list[Prediction] = []

    for step, value in enumerate(
        predicted,
        start=1,
    ):
        width = (
            spread.get(step, 0.0)
            * band_multiplier
        )

        predictions.append(
            Prediction(
                day=last_day
                + timedelta(days=step),
                predicted=round(value, 2),
                lower=round(
                    max(0.0, value - width),
                    2,
                ),
                upper=round(
                    value + width,
                    2,
                ),
            )
        )

    return predictions
