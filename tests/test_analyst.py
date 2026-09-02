from __future__ import annotations

"""
Analyst tests.

Every one of these runs offline. Gemini is replaced by
an httpx MockTransport, so the suite never spends money
and never depends on the network.
"""

import json

import httpx
import pytest

from analyst.client import (
    AnalystAuthError,
    AnalystError,
    GeminiClient,
)
from analyst.config import GeminiConfig
from analyst.prompt import SECTIONS, SYSTEM_PROMPT


def make_config() -> GeminiConfig:
    return GeminiConfig(
        api_key="test-key",
        model_name="gemini-3.5-flash-lite",
    )


def transport(
    handler,
) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
    )


def reply(text: str) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ]
    }


# ============================================================
# Config
# ============================================================


def test_model_name_strips_models_prefix() -> None:
    config = GeminiConfig(
        api_key="k",
        model_name="models/gemini-3.5-flash-lite",
    )

    assert (
        config.model_name
        == "gemini-3.5-flash-lite"
    )


def test_model_name_rejects_a_pasted_prompt() -> None:
    """
    The system prompt was once pasted in as the model
    id. A multi-word value must fail loudly rather than
    become part of a request URL.
    """

    with pytest.raises(ValueError):
        GeminiConfig(
            api_key="k",
            model_name=(
                "You are Store Pulse Analyst, an AI "
                "analytics assistant."
            ),
        )


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        GeminiConfig(
            api_key="   ",
            model_name="gemini-3.5-flash-lite",
        )


def test_generate_url_shape() -> None:
    assert make_config().generate_url == (
        "https://generativelanguage.googleapis.com"
        "/v1beta/models/"
        "gemini-3.5-flash-lite:generateContent"
    )


# ============================================================
# Client
# ============================================================


def test_api_key_travels_in_the_header_not_the_url() -> None:
    """
    The key must never reach a URL, where it would be
    captured by access logs and proxy traces.
    """

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["header"] = request.headers.get(
            "x-goog-api-key"
        )

        return httpx.Response(
            200,
            json=reply("ok"),
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        client.generate(
            system_prompt="s",
            user_prompt="u",
        )

    assert seen["header"] == "test-key"
    assert "test-key" not in seen["url"]
    assert "key=" not in seen["url"]


def test_system_prompt_is_sent_as_system_instruction() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(
            request.content.decode()
        )

        return httpx.Response(
            200,
            json=reply("ok"),
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        client.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt="question",
        )

    assert (
        seen["body"]["system_instruction"]["parts"][0][
            "text"
        ]
        == SYSTEM_PROMPT
    )


def test_history_becomes_earlier_contents_turns() -> None:
    """
    The conversation is what makes a follow-up
    answerable, and Gemini only sees it if the earlier
    turns are sent as `contents` ahead of the question.
    """

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(
            request.content.decode()
        )

        return httpx.Response(
            200,
            json=reply("ok"),
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        client.generate(
            system_prompt="s",
            user_prompt="why?",
            history=[
                {
                    "role": "user",
                    "text": "first question",
                },
                {
                    "role": "model",
                    "text": "first answer",
                },
            ],
        )

    contents = seen["body"]["contents"]

    assert [turn["role"] for turn in contents] == [
        "user",
        "model",
        "user",
    ]

    # The live question is last, so it is what the model
    # is answering.
    assert (
        contents[-1]["parts"][0]["text"] == "why?"
    )

    assert (
        contents[0]["parts"][0]["text"]
        == "first question"
    )


def test_no_history_still_sends_a_single_turn() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(
            request.content.decode()
        )

        return httpx.Response(
            200,
            json=reply("ok"),
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        client.generate(
            system_prompt="s",
            user_prompt="u",
        )

    assert len(seen["body"]["contents"]) == 1


def test_404_names_the_model_setting() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        with pytest.raises(AnalystError) as info:
            client.generate(
                system_prompt="s",
                user_prompt="u",
            )

    assert "GEMINI_MODEL" in str(info.value)


def test_403_is_an_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {"message": "denied"},
            },
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        with pytest.raises(AnalystAuthError):
            client.generate(
                system_prompt="s",
                user_prompt="u",
            )


def test_truncated_answer_explains_itself() -> None:
    """
    A reply cut off by the token budget arrives as a
    candidate with no text at all, which is otherwise
    indistinguishable from a silent failure.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [],
                            "role": "model",
                        },
                        "finishReason": "MAX_TOKENS",
                    }
                ]
            },
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        with pytest.raises(AnalystError) as info:
            client.generate(
                system_prompt="s",
                user_prompt="u",
            )

    assert "token limit" in str(info.value)


def test_blocked_prompt_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "promptFeedback": {
                    "blockReason": "SAFETY",
                },
            },
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        with pytest.raises(AnalystError) as info:
            client.generate(
                system_prompt="s",
                user_prompt="u",
            )

    assert "SAFETY" in str(info.value)


def test_retries_a_500_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1

        if calls["n"] == 1:
            return httpx.Response(500, json={})

        return httpx.Response(
            200,
            json=reply("recovered"),
        )

    with GeminiClient(
        make_config(),
        http_client=transport(handler),
    ) as client:
        answer = client.generate(
            system_prompt="s",
            user_prompt="u",
        )

    assert answer == "recovered"
    assert calls["n"] == 2


# ============================================================
# Prompt
# ============================================================


def test_prompt_states_the_read_only_stance() -> None:
    assert (
        "You DO NOT perform any Shopify write operation."
        in SYSTEM_PROMPT
    )


def test_prompt_defines_the_three_labels() -> None:
    for label in (
        "OBSERVED",
        "FORECAST",
        "INFERENCE",
    ):
        assert label in SYSTEM_PROMPT


def test_sections_match_the_prompt() -> None:
    """
    The frontend lays the answer out by these headings,
    so they must not drift from the prompt that asks
    for them.
    """

    for name in SECTIONS:
        assert name in SYSTEM_PROMPT
