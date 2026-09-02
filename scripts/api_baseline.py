from __future__ import annotations

"""
Record and compare API responses.

The API layer has no tests, so a refactor has no
safety net. This script freezes every endpoint's
current response to disk, then compares later runs
against it.

    python -m scripts.api_baseline record
    python -m scripts.api_baseline compare

`compare` exits non-zero when any response changed,
so it can gate each refactor step.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


BASELINE_DIR = Path(
    "tests/baseline/api"
)


# Every endpoint, with the parameter combinations
# worth pinning. Keep the boundary values: they are
# where a refactor is most likely to drift.
REQUESTS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "health",
        "/api/health",
        {},
    ),
    (
        "overview_default",
        "/api/overview",
        {},
    ),
    (
        "overview_min_days",
        "/api/overview",
        {"days": 1},
    ),
    (
        "overview_max_days",
        "/api/overview",
        {"days": 60},
    ),
    (
        "overview_days_7",
        "/api/overview",
        {"days": 7},
    ),
    (
        "inventory_default",
        "/api/inventory",
        {},
    ),
    (
        "inventory_threshold_0",
        "/api/inventory",
        {"threshold": 0},
    ),
    (
        "inventory_search",
        "/api/inventory",
        {
            "search": "a",
            "limit": 25,
        },
    ),
    (
        "inventory_limit_1",
        "/api/inventory",
        {"limit": 1},
    ),
    (
        "funnel",
        "/api/funnel",
        {},
    ),
    (
        "signals",
        "/api/signals",
        {},
    ),
    (
        "data_health",
        "/api/data-health",
        {},
    ),
    (
        "forecast_default",
        "/api/forecast",
        {},
    ),
    (
        "forecast_max_horizon",
        "/api/forecast",
        {"horizon": 14},
    ),
    (
        "forecast_revenue",
        "/api/forecast",
        {"metric": "revenue"},
    ),
]


# Fields that legitimately change between runs and
# must not be treated as a refactor regression.
VOLATILE_KEYS = {
    "generated_at",
    "checked_at",
    "database",
}


def strip_volatile(
    value: Any,
) -> Any:
    """
    Blank out timestamps and absolute paths so the
    comparison only sees real payload changes.
    """

    if isinstance(value, dict):
        return {
            key: (
                "<volatile>"
                if key in VOLATILE_KEYS
                else strip_volatile(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            strip_volatile(item)
            for item in value
        ]

    return value


def capture() -> dict[str, Any]:
    # Imported lazily so `record` always reads the
    # current state of the module under refactor.
    from api.app import app

    client = TestClient(app)

    captured: dict[str, Any] = {}

    for name, path, params in REQUESTS:
        response = client.get(
            path,
            params=params,
        )

        try:
            body = response.json()

        except ValueError:
            body = {
                "_raw": response.text[:2000]
            }

        captured[name] = {
            "path": path,
            "params": params,
            "status": response.status_code,
            "body": strip_volatile(body),
        }

    return captured


def baseline_file(
    name: str,
) -> Path:
    return BASELINE_DIR / f"{name}.json"


def record() -> int:
    BASELINE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    captured = capture()

    for name, payload in captured.items():
        baseline_file(name).write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n"
        )

        status = payload["status"]

        size = len(
            json.dumps(
                payload["body"],
                default=str,
            )
        )

        print(
            f"[OK] {name:<24} "
            f"status={status} "
            f"{size:>8,} bytes"
        )

    print()
    print(
        f"[PASS] Recorded "
        f"{len(captured)} responses to "
        f"{BASELINE_DIR}"
    )

    return 0


def compare() -> int:
    if not BASELINE_DIR.exists():
        print(
            "[FAIL] No baseline recorded. "
            "Run: python -m scripts.api_baseline "
            "record",
            file=sys.stderr,
        )
        return 1

    captured = capture()

    failures: list[str] = []

    for name, payload in captured.items():
        path = baseline_file(name)

        if not path.exists():
            failures.append(
                f"{name}: no baseline file"
            )
            continue

        expected = json.loads(
            path.read_text()
        )

        actual = json.loads(
            json.dumps(
                payload,
                sort_keys=True,
                default=str,
            )
        )

        if actual == expected:
            print(f"[OK]   {name}")
            continue

        failures.append(name)

        print(f"[DIFF] {name}")

        if actual["status"] != expected["status"]:
            print(
                f"       status "
                f"{expected['status']} -> "
                f"{actual['status']}"
            )

    print()

    if failures:
        print(
            "[FAIL] Changed responses: "
            + ", ".join(failures),
            file=sys.stderr,
        )
        return 1

    print(
        f"[PASS] All {len(captured)} responses "
        "unchanged"
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Record or compare API responses "
            "around a refactor."
        )
    )

    parser.add_argument(
        "action",
        choices=["record", "compare"],
    )

    args = parser.parse_args()

    if args.action == "record":
        return record()

    return compare()


if __name__ == "__main__":
    sys.exit(main())
