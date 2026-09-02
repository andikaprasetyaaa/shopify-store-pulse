from __future__ import annotations

"""
Funnel payload from the latest ShopifyQL session
snapshot.
"""

from typing import Any

from analytics.metrics import (
    StorePulseMetrics,
)
from api.deps import (
    database_path,
    require_database,
)
from api.formatting import (
    iso_value,
)


def build_funnel() -> dict[str, Any]:
    require_database()

    with StorePulseMetrics(
        database_path()
    ) as metrics:
        result = (
            metrics
            .latest_funnel_metrics()
        )

    if result is None:
        return {
            "available":
                False,

            "data":
                None,
        }

    return {
        "available":
            True,

        "data":
            {
                key:
                    (
                        iso_value(
                            value
                        )
                        if key
                        == "snapshot_at"
                        else value
                    )
                for (
                    key,
                    value,
                ) in result.items()
            },
    }
