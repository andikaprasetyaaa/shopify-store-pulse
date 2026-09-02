from __future__ import annotations

from datetime import date, timedelta

import pytest

from analytics.forecast import (
    BENCHMARK,
    MODELS,
    WEEK,
    ForecastError,
    Point,
    backtest,
    damped_trend,
    forecast,
    mean_7,
    naive,
    seasonal_naive,
    summarize,
    weekday_factors,
    weekday_profile,
)


def flat(
    value: float,
    days: int,
) -> list[float]:
    return [value] * days


def weekly(
    pattern: list[float],
    weeks: int,
) -> list[float]:
    return pattern * weeks


# ============================================================
# Models
# ============================================================


def test_naive_repeats_last_value() -> None:
    assert naive([1, 2, 3], 3) == [3, 3, 3]


def test_mean_7_averages_the_week() -> None:
    history = [
        10, 10, 10, 10, 10, 10, 24,
    ]

    assert mean_7(history, 2) == [12.0, 12.0]


def test_seasonal_naive_repeats_the_week() -> None:
    history = [
        1, 2, 3, 4, 5, 6, 7,
    ]

    assert seasonal_naive(history, 9) == [
        1, 2, 3, 4, 5, 6, 7, 1, 2,
    ]


def test_seasonal_naive_falls_back_when_short() -> None:
    """
    With under a week of history there is no weekday
    to repeat, so it must degrade to naive rather
    than index out of range.
    """

    assert seasonal_naive([5, 9], 3) == [9, 9, 9]


def test_weekday_factors_find_the_pattern() -> None:
    pattern = [
        50, 100, 100, 100, 100, 100, 150,
    ]

    factors = weekday_factors(
        weekly(pattern, 8)
    )

    assert factors[0] == pytest.approx(
        0.5,
        rel=0.01,
    )

    assert factors[6] == pytest.approx(
        1.5,
        rel=0.01,
    )


def test_weekday_factors_survive_all_zero() -> None:
    """
    A store with no orders must not divide by zero.
    """

    assert weekday_factors(
        flat(0.0, 28)
    ) == [1.0] * WEEK


def test_weekday_profile_reproduces_the_shape() -> None:
    pattern = [
        50, 100, 100, 100, 100, 100, 150,
    ]

    predictions = weekday_profile(
        weekly(pattern, 8),
        WEEK,
    )

    for predicted, expected in zip(
        predictions,
        pattern,
    ):
        assert predicted == pytest.approx(
            expected,
            rel=0.05,
        )


def test_weekday_profile_falls_back_when_short() -> None:
    history = [1, 2, 3, 4, 5, 6, 7, 8]

    assert weekday_profile(
        history,
        3,
    ) == seasonal_naive(history, 3)


def test_damped_trend_follows_growth() -> None:
    """
    On a rising series the forecast must keep rising.

    It starts below the last observed value on
    purpose: the level is the trailing weekly mean,
    which sits in the middle of a rising week rather
    than at its top.
    """

    history = [
        float(day) for day in range(1, 43)
    ]

    predictions = damped_trend(history, 5)

    assert predictions == sorted(predictions)

    assert predictions[-1] > predictions[0]


def test_flat_series_gives_a_flat_forecast() -> None:
    """
    No trend to extrapolate means no drift.
    """

    predictions = damped_trend(
        flat(100.0, 42),
        5,
    )

    for value in predictions:
        assert value == pytest.approx(
            100.0,
            rel=0.01,
        )


def test_damped_trend_does_not_run_away() -> None:
    """
    Damping is the whole point: 60 days of a growing
    store must not extrapolate into a straight line
    to infinity.
    """

    history = [
        float(day) for day in range(1, 43)
    ]

    predictions = damped_trend(
        history,
        30,
    )

    undamped = history[-1] + 30

    assert predictions[-1] < undamped


def test_no_model_returns_negative_values() -> None:
    history = [
        float(50 - day) for day in range(42)
    ]

    for name, model in MODELS.items():
        for value in model(history, 14):
            assert value >= 0.0, name


def test_every_model_returns_the_horizon() -> None:
    history = flat(10.0, 42)

    for name, model in MODELS.items():
        assert len(
            model(history, 11)
        ) == 11, name


# ============================================================
# Backtest
# ============================================================


def test_backtest_needs_enough_history() -> None:
    with pytest.raises(ForecastError):
        backtest(
            flat(10.0, 10),
            min_train=28,
        )


def test_backtest_scores_every_horizon() -> None:
    scores = backtest(
        weekly(
            [50, 100, 100, 100, 100, 100, 150],
            8,
        ),
        horizon=7,
    )

    horizons = {
        score.horizon for score in scores
    }

    assert horizons == set(range(1, 8))


def test_perfect_pattern_scores_near_zero() -> None:
    """
    On a noiseless repeating series the seasonal
    model must be almost exactly right. If this
    drifts, the backtest wiring is wrong.
    """

    scores = backtest(
        weekly(
            [50, 100, 100, 100, 100, 100, 150],
            10,
        ),
        horizon=7,
        models={
            "seasonal_naive": seasonal_naive,
        },
    )

    for score in scores:
        assert score.mape < 0.01


def test_backtest_does_not_leak_the_future() -> None:
    """
    A model that could see past the cutoff would score
    perfectly on a series it cannot possibly know.
    Appending a wild jump must not improve the score
    of the days before it.
    """

    history = flat(100.0, 40)

    clean = summarize(
        backtest(
            history,
            horizon=3,
            models={"mean_7": mean_7},
        )
    )["mean_7"]

    spiked = summarize(
        backtest(
            history + [10000.0],
            horizon=3,
            models={"mean_7": mean_7},
        )
    )["mean_7"]

    assert spiked > clean


def test_summarize_ranks_models() -> None:
    ranking = summarize(
        backtest(
            weekly(
                [
                    50, 100, 100, 100,
                    100, 100, 150,
                ],
                9,
            ),
            horizon=7,
        )
    )

    assert set(ranking) == set(MODELS)

    assert ranking[BENCHMARK] < ranking["naive"]


# ============================================================
# Forecast output
# ============================================================


def make_points(
    values: list[float],
) -> list[Point]:
    start = date(2026, 7, 1)

    return [
        Point(
            day=start + timedelta(days=offset),
            value=value,
        )
        for offset, value in enumerate(values)
    ]


def test_forecast_starts_the_day_after_history() -> None:
    points = make_points(flat(100.0, 42))

    predictions = forecast(
        points,
        horizon=3,
    )

    assert predictions[0].day == (
        points[-1].day + timedelta(days=1)
    )

    assert len(predictions) == 3


def test_forecast_band_contains_the_estimate() -> None:
    predictions = forecast(
        make_points(
            weekly(
                [
                    50, 100, 100, 100,
                    100, 100, 150,
                ],
                8,
            )
        ),
        horizon=7,
    )

    for prediction in predictions:
        assert (
            prediction.lower
            <= prediction.predicted
            <= prediction.upper
        )


def test_band_widens_with_the_horizon() -> None:
    """
    Uncertainty grows further out, and the chart must
    be able to show that honestly.
    """

    predictions = forecast(
        make_points(
            [
                100.0 + (offset % 7) * 10
                for offset in range(60)
            ]
        ),
        horizon=14,
    )

    first = (
        predictions[0].upper
        - predictions[0].lower
    )

    last = (
        predictions[-1].upper
        - predictions[-1].lower
    )

    assert last > first


def test_band_never_goes_negative() -> None:
    predictions = forecast(
        make_points(flat(1.0, 42)),
        horizon=14,
    )

    for prediction in predictions:
        assert prediction.lower >= 0.0


def test_forecast_rejects_empty_history() -> None:
    with pytest.raises(ForecastError):
        forecast([], horizon=7)


def test_forecast_rejects_unknown_model() -> None:
    with pytest.raises(ForecastError):
        forecast(
            make_points(flat(10.0, 42)),
            model_name="magic",
        )


def test_forecast_works_without_enough_backtest() -> None:
    """
    Too little history to measure a band must still
    produce a forecast, just without a band.
    """

    predictions = forecast(
        make_points(flat(10.0, 10)),
        horizon=3,
    )

    assert len(predictions) == 3

    for prediction in predictions:
        assert prediction.lower == (
            prediction.predicted
        )


def test_forecast_sorts_unordered_history() -> None:
    points = make_points(flat(100.0, 42))

    shuffled = list(reversed(points))

    assert forecast(
        shuffled,
        horizon=2,
    )[0].day == forecast(
        points,
        horizon=2,
    )[0].day
