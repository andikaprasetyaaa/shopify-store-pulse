from __future__ import annotations

"""
Analyst routes.

The analyst is a read-only explainer over data the
other endpoints already serve, so it lives behind its
own router and its own configuration check: the rest of
the dashboard has to keep working when GEMINI_API_KEY is
absent.
"""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.analyst import analyse, analyst_status

router = APIRouter(
    tags=["analyst"],
)


class AnalystTurn(BaseModel):
    """
    One earlier message in the conversation.

    The transcript lives in the browser, so it arrives
    here as ordinary request input and is bounded like
    any other: an unbounded history would let a single
    request carry an arbitrarily large prompt to a
    metered API.
    """

    role: Literal["user", "model"]

    text: str = Field(
        max_length=20000,
    )


class AnalystRequest(BaseModel):
    """One question, plus the slice to reason over."""

    question: str | None = Field(
        default=None,
        max_length=2000,
    )

    history: list[AnalystTurn] = Field(
        default_factory=list,
        max_length=40,
    )

    days: int = Field(
        default=30,
        ge=7,
        le=60,
    )

    forecast_metric: str = Field(
        default="orders",
        pattern="^(orders|revenue)$",
    )

    forecast_horizon: int = Field(
        default=7,
        ge=1,
        le=14,
    )


@router.get("/api/analyst/status")
def status() -> dict[str, Any]:
    return analyst_status()


@router.post("/api/analyst")
def ask(
    request: AnalystRequest,
) -> dict[str, Any]:
    return analyse(
        request.question,
        days=request.days,
        forecast_metric=request.forecast_metric,
        forecast_horizon=request.forecast_horizon,
        history=[
            turn.model_dump()
            for turn in request.history
        ],
    )
