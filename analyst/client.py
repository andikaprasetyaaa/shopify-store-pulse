from __future__ import annotations

"""
Minimal Gemini client for the analyst endpoint.

Deliberately small: one call, one shape of response.
The API key travels in the `x-goog-api-key` header
rather than the `?key=` query parameter, so it does not
end up in access logs, proxy traces or error strings -
and because the query-parameter form was observed to
answer 404 for this model while the header form works.
"""

from collections.abc import Sequence
from typing import Any, Literal, TypedDict

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from analyst.config import GeminiConfig


class Turn(TypedDict):
    """
    One completed exchange in the conversation.

    `role` uses Gemini's own vocabulary - "user" and
    "model" - so a turn can be handed to the API without
    translation.
    """

    role: Literal["user", "model"]
    text: str


class AnalystError(RuntimeError):
    """Base failure for the analyst."""


class AnalystAuthError(AnalystError):
    """The key was rejected."""


class _RetryableAnalystError(AnalystError):
    """Internal: a 429 or 5xx worth retrying."""


class GeminiClient:
    """Text generation against Gemini, with or without history."""

    def __init__(
        self,
        config: GeminiConfig,
        *,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.config = config

        self._owns_http_client = http_client is None

        self._http = http_client or httpx.Client(
            timeout=timeout_seconds,
        )

    def __enter__(self) -> "GeminiClient":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        history: Sequence[Turn] | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
    ) -> str:
        """
        Return the model's text for one prompt.

        `history` is the conversation so far, oldest
        first, and is sent ahead of `user_prompt` as
        earlier turns. Only the final turn carries the
        data snapshot: repeating a 30 kB JSON block on
        every turn would cost more with each question
        and give the model several stale copies of the
        same figures to choose between.

        Temperature is low by default: this assistant
        explains supplied numbers, and creativity in
        that job shows up as invention.
        """

        contents: list[dict[str, Any]] = [
            {
                "role": turn["role"],
                "parts": [
                    {"text": turn["text"]},
                ],
            }
            for turn in (history or ())
        ]

        contents.append(
            {
                "role": "user",
                "parts": [
                    {"text": user_prompt},
                ],
            }
        )

        payload: dict[str, Any] = {
            "system_instruction": {
                "parts": [
                    {"text": system_prompt},
                ],
            },
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }

        response = self._post(payload)

        if response.status_code in (401, 403):
            raise AnalystAuthError(
                "Gemini rejected the API key "
                f"(HTTP {response.status_code}). "
                "Check GEMINI_API_KEY."
            )

        if response.status_code == 404:
            raise AnalystError(
                "Gemini has no model named "
                f"'{self.config.model_name}'. "
                "Check GEMINI_MODEL."
            )

        if response.status_code >= 400:
            raise AnalystError(
                "Gemini request failed with HTTP "
                f"{response.status_code}: "
                f"{_error_message(response)}"
            )

        try:
            body = response.json()

        except ValueError as exc:
            raise AnalystError(
                "Gemini returned a non-JSON response."
            ) from exc

        return _extract_text(body)

    @retry(
        retry=retry_if_exception_type(
            (
                httpx.TransportError,
                _RetryableAnalystError,
            )
        ),
        wait=wait_exponential(
            multiplier=0.5,
            min=0.5,
            max=8,
        ),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _post(
        self,
        payload: dict[str, Any],
    ) -> httpx.Response:
        response = self._http.post(
            self.config.generate_url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": (
                    self.config.api_key
                    .get_secret_value()
                ),
            },
            json=payload,
        )

        if (
            response.status_code == 429
            or response.status_code >= 500
        ):
            raise _RetryableAnalystError(
                "Retryable Gemini HTTP status: "
                f"{response.status_code}"
            )

        return response


def _error_message(
    response: httpx.Response,
) -> str:
    try:
        body = response.json()

    except ValueError:
        return response.text[:200]

    error = body.get("error")

    if isinstance(error, dict):
        return str(
            error.get(
                "message",
                "unknown error",
            )
        )[:300]

    return "unknown error"


def _extract_text(
    body: dict[str, Any],
) -> str:
    """
    Pull the answer out of a generateContent response.

    Two failure modes get their own message because
    both are silent otherwise: a prompt blocked by a
    safety filter returns no candidate at all, and a
    reply cut off by the token budget returns a
    candidate whose parts are empty.
    """

    feedback = body.get("promptFeedback")

    if (
        isinstance(feedback, dict)
        and feedback.get("blockReason")
    ):
        raise AnalystError(
            "Gemini blocked the prompt: "
            f"{feedback.get('blockReason')}"
        )

    candidates = body.get("candidates")

    if not isinstance(candidates, list) or not candidates:
        raise AnalystError(
            "Gemini returned no candidates."
        )

    candidate = candidates[0]

    parts = (
        candidate.get("content", {}).get("parts")
        if isinstance(candidate, dict)
        else None
    )

    text = "".join(
        part.get("text", "")
        for part in (parts or [])
        if isinstance(part, dict)
    ).strip()

    if text:
        return text

    reason = (
        candidate.get("finishReason")
        if isinstance(candidate, dict)
        else None
    )

    if reason == "MAX_TOKENS":
        raise AnalystError(
            "Gemini hit the output token limit before "
            "producing any text. Raise "
            "max_output_tokens or narrow the question."
        )

    raise AnalystError(
        "Gemini returned an empty answer "
        f"(finishReason={reason})."
    )
