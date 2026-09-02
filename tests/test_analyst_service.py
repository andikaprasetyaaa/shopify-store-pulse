from __future__ import annotations

"""
Service and route tests for the analyst.

The context builder is stubbed so these stay hermetic:
they are about orchestration, caching and error
handling, not about DuckDB.
"""

import json

import pytest
from fastapi.testclient import TestClient

import services.analyst as analyst_service
from analyst.client import AnalystError
from analyst.prompt import SECTIONS
from api.app import app


FAKE_CONTEXT = {
    "observed": {
        "period": {"current": {"orders": 10}},
        "anomaly_caveat": None,
    },
    "forecast": {
        "metric": "orders",
        "model": "damped_trend",
        "predictions": [
            {
                "day": "2026-09-03",
                "predicted": 12.0,
                "lower": 9.0,
                "upper": 15.0,
            }
        ],
    },
    "data_coverage": {
        "order_start": "2026-07-03",
        "order_end": "2026-09-01",
    },
}


class StubClient:
    """Stands in for GeminiClient."""

    def __init__(
        self,
        answer: str = "stub answer",
        error: Exception | None = None,
    ) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[dict] = []
        self.closed = False

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> str:
        self.calls.append(
            {
                "system": system_prompt,
                "user": user_prompt,
            }
        )

        if self.error is not None:
            raise self.error

        return self.answer

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def stub_context(monkeypatch):
    monkeypatch.setattr(
        analyst_service,
        "build_context",
        lambda **kwargs: FAKE_CONTEXT,
    )

    # Every test starts with an empty cache, otherwise
    # order decides the result.
    analyst_service._cache.clear()

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-key",
    )

    monkeypatch.setenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    )


def test_missing_key_returns_an_error_not_an_exception(
    monkeypatch,
) -> None:
    """
    The dashboard must keep working without Gemini
    configured, so this path is a payload, not a 500.
    """

    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False,
    )

    monkeypatch.setattr(
        analyst_service.GeminiConfig,
        "from_env",
        classmethod(
            lambda cls: (_ for _ in ()).throw(
                analyst_service.AnalystConfigError(
                    "GEMINI_API_KEY is not set."
                )
            )
        ),
    )

    result = analyst_service.analyse("why?")

    assert result["answer"] is None
    assert "GEMINI_API_KEY" in result["error"]


def test_answer_is_returned(monkeypatch) -> None:
    client = StubClient("the answer")

    result = analyst_service.analyse(
        "why did orders fall?",
        client=client,
    )

    assert result["answer"] == "the answer"
    assert result["error"] is None
    assert result["cached"] is False
    assert (
        result["question"] == "why did orders fall?"
    )


def test_injected_client_is_not_closed() -> None:
    """
    Only a client the service created is its to close.
    """

    client = StubClient()

    analyst_service.analyse(
        "q",
        client=client,
    )

    assert client.closed is False


def test_blank_question_falls_back_to_the_default() -> None:
    client = StubClient()

    result = analyst_service.analyse(
        "   ",
        client=client,
    )

    assert (
        result["question"]
        == analyst_service.DEFAULT_QUESTION
    )


def test_identical_question_is_served_from_cache() -> None:
    client = StubClient()

    first = analyst_service.analyse(
        "same question",
        client=client,
    )

    second = analyst_service.analyse(
        "same question",
        client=client,
    )

    assert first["cached"] is False
    assert second["cached"] is True

    # The point of the cache: one billed call, not two.
    assert len(client.calls) == 1


def test_a_different_question_is_not_cached() -> None:
    client = StubClient()

    analyst_service.analyse("one", client=client)
    analyst_service.analyse("two", client=client)

    assert len(client.calls) == 2


def test_gemini_failure_becomes_an_error_payload() -> None:
    client = StubClient(
        error=AnalystError("upstream exploded"),
    )

    result = analyst_service.analyse(
        "q",
        client=client,
    )

    assert result["answer"] is None
    assert "upstream exploded" in result["error"]


def test_user_prompt_carries_the_data_and_the_headings() -> None:
    prompt = analyst_service.build_user_prompt(
        "why?",
        FAKE_CONTEXT,
    )

    for name in SECTIONS:
        assert name in prompt

    # The forecast values must reach the model verbatim,
    # since it is forbidden from recomputing them.
    assert "damped_trend" in prompt
    assert json.dumps(12.0) in prompt


def test_context_carries_no_shopify_secret() -> None:
    client = StubClient()

    analyst_service.analyse("q", client=client)

    sent = client.calls[0]["user"]

    for leaked in (
        "SHOPIFY_CLIENT_SECRET",
        "shpss_",
        "GEMINI_API_KEY",
        "AIzaSy",
    ):
        assert leaked not in sent


# ============================================================
# Route
# ============================================================


def test_status_route_reports_configuration() -> None:
    with TestClient(app) as client:
        body = client.get(
            "/api/analyst/status"
        ).json()

    assert body["configured"] is True
    assert body["model"] == "gemini-3.5-flash-lite"


def test_ask_route_returns_the_answer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        analyst_service,
        "GeminiClient",
        lambda config: StubClient("routed answer"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/analyst",
            json={"question": "why?"},
        )

    assert response.status_code == 200
    assert (
        response.json()["answer"] == "routed answer"
    )


def test_ask_route_rejects_an_out_of_range_horizon() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/analyst",
            json={
                "question": "q",
                "forecast_horizon": 90,
            },
        )

    assert response.status_code == 422


def test_ask_route_rejects_an_unknown_metric() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/analyst",
            json={
                "question": "q",
                "forecast_metric": "profit",
            },
        )

    assert response.status_code == 422
