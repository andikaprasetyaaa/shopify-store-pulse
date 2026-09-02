from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import app
from services.forecast import (
    MAX_HORIZON,
    build_forecast,
)


@pytest.fixture(scope="module")
def payload() -> dict:
    return build_forecast(
        "orders",
        horizon=7,
    )


def test_history_and_forecast_do_not_overlap(
    payload: dict,
) -> None:
    """
    The chart draws these end to end, so a repeated
    day would render as a fork in the line.
    """

    history_days = {
        row["day"]
        for row in payload["history"]
    }

    forecast_days = {
        row["day"]
        for row in payload["forecast"]
    }

    assert not (
        history_days & forecast_days
    )


def test_forecast_starts_after_history(
    payload: dict,
) -> None:
    last_actual = max(
        row["day"]
        for row in payload["history"]
    )

    first_forecast = min(
        row["day"]
        for row in payload["forecast"]
    )

    assert first_forecast > last_actual


def test_band_brackets_every_prediction(
    payload: dict,
) -> None:
    for row in payload["forecast"]:
        assert (
            row["lower"]
            <= row["predicted"]
            <= row["upper"]
        )


def test_accuracy_reports_against_benchmark(
    payload: dict,
) -> None:
    """
    The number on screen has to carry its own track
    record, including what it is being compared to.
    """

    accuracy = payload["accuracy"]

    assert accuracy is not None
    assert accuracy["benchmark"] == (
        "seasonal_naive"
    )
    assert accuracy["model_mape"] > 0
    assert accuracy["folds"] > 0


def test_horizon_is_clamped() -> None:
    """
    Beyond two weeks the model stops beating the
    benchmark, so a larger request must be capped
    rather than served.
    """

    payload = build_forecast(
        "orders",
        horizon=999,
    )

    assert len(
        payload["forecast"]
    ) == MAX_HORIZON


def test_endpoint_rejects_unknown_metric() -> None:
    client = TestClient(app)

    assert client.get(
        "/api/forecast",
        params={"metric": "profit"},
    ).status_code == 422


def test_endpoint_rejects_oversized_horizon() -> None:
    client = TestClient(app)

    assert client.get(
        "/api/forecast",
        params={"horizon": 30},
    ).status_code == 422
