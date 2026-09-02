from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from api.formatting import (
    iso_value,
    number,
    percent_change,
    serialize_anomaly,
)


def test_iso_value_handles_none() -> None:
    assert iso_value(None) is None


def test_iso_value_formats_dates() -> None:
    assert iso_value(
        date(2026, 9, 1)
    ) == "2026-09-01"

    assert iso_value(
        datetime(
            2026,
            9,
            1,
            8,
            0,
            tzinfo=timezone.utc,
        )
    ) == "2026-09-01T08:00:00+00:00"


def test_iso_value_falls_back_to_str() -> None:
    assert iso_value(42) == "42"


def test_number_treats_none_as_zero() -> None:
    assert number(None) == 0.0


def test_number_converts_decimal() -> None:
    assert number(
        Decimal("12.50")
    ) == 12.5


def test_percent_change_is_rounded() -> None:
    assert percent_change(
        Decimal("150"),
        Decimal("100"),
    ) == 50.0

    assert percent_change(
        Decimal("50"),
        Decimal("100"),
    ) == -50.0


def test_percent_change_guards_zero_baseline() -> None:
    """
    Dividing by a zero baseline must return None
    rather than raising or reporting infinity.
    """

    assert percent_change(
        Decimal("100"),
        Decimal("0"),
    ) is None


def test_percent_change_accepts_ints() -> None:
    assert percent_change(3, 2) == 50.0


def make_anomaly(
    **overrides,
) -> dict:
    result = {
        "metric": "orders",
        "as_of_day": "2026-09-01",
        "current_value": Decimal("10"),
        "baseline_name": "trailing_28d",
        "baseline_value": Decimal("20"),
        "deviation_pct": Decimal("-50"),
        "direction": "down",
        "severity": "high",
        "reason": "below baseline",
        "currency_code": "USD",
    }

    result.update(overrides)

    return result


def test_serialize_anomaly_converts_decimals() -> None:
    payload = serialize_anomaly(
        make_anomaly()
    )

    assert payload["current_value"] == 10.0
    assert payload["baseline_value"] == 20.0
    assert payload["deviation_pct"] == -50.0
    assert payload["severity"] == "high"


def test_serialize_anomaly_keeps_nulls() -> None:
    """
    A missing baseline must stay null instead of
    being coerced to 0.0, which would read as a real
    measurement in the dashboard.
    """

    payload = serialize_anomaly(
        make_anomaly(
            baseline_value=None,
            deviation_pct=None,
        )
    )

    assert payload["baseline_value"] is None
    assert payload["deviation_pct"] is None
