from __future__ import annotations

"""
Value formatting shared by the API responses.

Pure functions only: no database access, no FastAPI,
no request state. Safe to unit test directly.
"""

from decimal import Decimal
from typing import Any


def iso_value(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if hasattr(
        value,
        "isoformat",
    ):
        return value.isoformat()

    return str(value)


def number(
    value: Any,
) -> float:
    if value is None:
        return 0.0

    return float(value)


def percent_change(
    current: Decimal | int,
    previous: Decimal | int,
) -> float | None:
    current_decimal = Decimal(
        str(current)
    )

    previous_decimal = Decimal(
        str(previous)
    )

    if previous_decimal == 0:
        return None

    result = (
        (
            current_decimal
            - previous_decimal
        )
        / previous_decimal
        * Decimal("100")
    )

    return round(
        float(result),
        2,
    )


def serialize_anomaly(
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "metric":
            result[
                "metric"
            ],

        "as_of_day":
            result[
                "as_of_day"
            ],

        "current_value":
            number(
                result[
                    "current_value"
                ]
            ),

        "baseline_name":
            result[
                "baseline_name"
            ],

        "baseline_value":
            (
                number(
                    result[
                        "baseline_value"
                    ]
                )
                if result[
                    "baseline_value"
                ]
                is not None
                else None
            ),

        "deviation_pct":
            (
                number(
                    result[
                        "deviation_pct"
                    ]
                )
                if result[
                    "deviation_pct"
                ]
                is not None
                else None
            ),

        "direction":
            result[
                "direction"
            ],

        "severity":
            result[
                "severity"
            ],

        "reason":
            result[
                "reason"
            ],

        "currency_code":
            result[
                "currency_code"
            ],
    }
