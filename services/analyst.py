from __future__ import annotations

"""
The analyst service.

Assembles a compact, factual snapshot of the store and
hands it to Gemini together with the system prompt.

The whole design rests on one idea: the model is an
explainer, not a calculator. Every number it is allowed
to cite is computed here, by the same services the
dashboard renders from, so the answer cannot disagree
with the screen. Nothing raw from Shopify is sent - only
what the analytics layer has already derived.
"""

import hashlib
import json
import time
from datetime import date
from typing import Any

from analyst.client import (
    AnalystError,
    GeminiClient,
)
from analyst.config import (
    AnalystConfigError,
    GeminiConfig,
)
from analyst.prompt import (
    DEFAULT_QUESTION,
    SECTIONS,
    SYSTEM_PROMPT,
)
from services.forecast import build_forecast
from services.inventory import build_inventory
from services.metadata import database_metadata
from services.overview import build_overview
from services.signals import build_signals

# How many low-stock rows travel with the context. The
# model needs a sense of the risk, not the whole table,
# and 70k variants would not fit anyway.
RISK_SAMPLE = 15

CACHE_TTL_SECONDS = 300

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def build_context(
    days: int = 30,
    forecast_metric: str = "orders",
    forecast_horizon: int = 7,
    low_stock_threshold: int = 5,
) -> dict[str, Any]:
    """
    The factual snapshot the model is allowed to cite.

    Each block is labelled with what it is, because the
    prompt asks the model to keep OBSERVED separate from
    FORECAST and it can only do that if the input says
    which is which.
    """

    overview = build_overview(days)

    signals = build_signals()

    forecast = build_forecast(
        forecast_metric,
        forecast_horizon,
    )

    inventory = build_inventory(
        low_stock_threshold,
        "",
        RISK_SAMPLE,
    )

    metadata = database_metadata()

    return {
        "observed": {
            "reporting_window_days": days,
            "period": {
                "current": overview["current"],
                "previous": overview["previous"],
                "change_pct": overview["changes_pct"],
            },
            "daily_trend": overview["trend"],
            "inventory_summary": inventory["summary"],
            "low_stock_threshold": (
                low_stock_threshold
            ),
            "low_stock_sample": inventory["items"],
            "funnel": overview["funnel"],
            "anomaly_signals": signals["signals"],
            "anomaly_error": signals["error"],
            "anomaly_caveat": _anomaly_caveat(
                signals["signals"],
            ),
        },
        "forecast": {
            "metric": forecast["metric"],
            "model": forecast["model"],
            "predictions": forecast["forecast"],
            "band_meaning": (
                "lower and upper bound an 80% "
                "interval derived from the model's "
                "backtested mean absolute error at "
                "each horizon"
            ),
            "backtest": forecast["accuracy"],
            "backtest_meaning": (
                "model_mape and benchmark_mape are "
                "mean absolute percentage error from a "
                "rolling-origin backtest; lower is "
                "better. The benchmark is a seasonal "
                "naive model. folds is the number of "
                "scored predictions."
            ),
            "error": forecast["error"],
        },
        "data_coverage": {
            "order_start": metadata.get("order_start"),
            "order_end": metadata.get("order_end"),
            "orders_synced_at": metadata.get(
                "orders_synced_at"
            ),
            "inventory_synced_at": metadata.get(
                "inventory_synced_at"
            ),
            "analytics_synced_at": metadata.get(
                "analytics_synced_at"
            ),
            "note": (
                "The read_orders scope exposes about "
                "60 days, so no year-over-year "
                "comparison is possible."
            ),
        },
    }


def _anomaly_caveat(
    signals: dict[str, Any],
) -> str | None:
    """
    Warn when the anomaly signals are scored against
    today.

    The baseline engine takes the latest day present in
    the data (analytics/baseline.py), which during
    trading hours is a day that is still accumulating
    orders. Comparing a part-day against a mean of whole
    days makes every morning look like a 50% collapse.
    The forecast avoids this by excluding today
    outright; the signals do not, so the analyst is told
    rather than left to report a daily false alarm as
    its headline finding.
    """

    days = {
        signal.get("as_of_day")
        for signal in signals.values()
        if isinstance(signal, dict)
    }

    today = date.today().isoformat()

    if today not in days:
        return None

    return (
        f"anomaly_signals are scored as of {today}, "
        "which is the current day and is still "
        "accumulating orders. A part-day compared "
        "against a baseline of whole days will show a "
        "large negative deviation for purely mechanical "
        "reasons. Treat a downside signal dated today "
        "as inconclusive unless the deviation is far "
        "larger than the share of the day still "
        "remaining, and say so rather than reporting it "
        "as an established drop."
    )


def build_user_prompt(
    question: str,
    context: dict[str, Any],
) -> str:
    """
    The user turn: the question, then the data.

    The instruction to use only this data is repeated
    here as well as in the system prompt, because it is
    the single rule most worth reinforcing next to the
    numbers themselves.
    """

    return (
        f"Question: {question}\n\n"
        "Answer using only the data below. Do not "
        "compute new metrics and do not alter the "
        "forecast values. If the data does not support "
        "an answer, say so explicitly.\n\n"
        "Structure your answer with these six "
        "headings, in this order:\n"
        + "\n".join(
            f"{index}. {name}"
            for index, name in enumerate(
                SECTIONS,
                start=1,
            )
        )
        + "\n\nDATA (JSON):\n"
        + json.dumps(
            context,
            indent=2,
            default=str,
        )
    )


def _cache_key(
    question: str,
    context: dict[str, Any],
    model_name: str,
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            context,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    return f"{model_name}|{question}|{digest}"


def analyse(
    question: str | None = None,
    *,
    days: int = 30,
    forecast_metric: str = "orders",
    forecast_horizon: int = 7,
    client: GeminiClient | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """
    Answer one question about the current store state.

    Identical questions over identical data are served
    from a short-lived cache: the dashboard's refresh
    button would otherwise bill a fresh generation for
    an answer that cannot have changed.
    """

    asked = (question or "").strip() or DEFAULT_QUESTION

    try:
        config = GeminiConfig.from_env()

    except (AnalystConfigError, ValueError) as exc:
        return {
            "question": asked,
            "answer": None,
            "model": None,
            "cached": False,
            "error": str(exc),
        }

    context = build_context(
        days=days,
        forecast_metric=forecast_metric,
        forecast_horizon=forecast_horizon,
    )

    key = _cache_key(
        asked,
        context,
        config.model_name,
    )

    now = time.monotonic()

    if use_cache:
        hit = _cache.get(key)

        if hit is not None and now - hit[0] < CACHE_TTL_SECONDS:
            return {**hit[1], "cached": True}

    owned = client is None

    active = client or GeminiClient(config)

    try:
        answer = active.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(
                asked,
                context,
            ),
        )

    except AnalystError as exc:
        return {
            "question": asked,
            "answer": None,
            "model": config.model_name,
            "cached": False,
            "error": str(exc),
        }

    finally:
        if owned:
            active.close()

    result = {
        "question": asked,
        "answer": answer,
        "model": config.model_name,
        "cached": False,
        "error": None,
        "context_summary": {
            "reporting_window_days": days,
            "forecast_metric": forecast_metric,
            "forecast_horizon": forecast_horizon,
            "order_start": context["data_coverage"][
                "order_start"
            ],
            "order_end": context["data_coverage"][
                "order_end"
            ],
        },
    }

    _cache[key] = (now, result)

    return result


def analyst_status() -> dict[str, Any]:
    """
    Whether the analyst is usable, without calling out
    to Gemini. The frontend asks this before offering
    the feature.
    """

    try:
        config = GeminiConfig.from_env()

    except (AnalystConfigError, ValueError) as exc:
        return {
            "configured": False,
            "model": None,
            "error": str(exc),
        }

    return {
        "configured": True,
        "model": config.model_name,
        "error": None,
    }
