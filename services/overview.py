from __future__ import annotations

"""
Overview payload: headline KPIs, trend series and
period-over-period comparison.
"""

from decimal import Decimal
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
    percent_change,
)
from services.signals import (
    load_signals,
)
from services.trends import (
    build_trend,
    filled_daily_series,
    summarize_period,
)


def build_overview(
    days: int,
) -> dict[str, Any]:
    require_database()

    with StorePulseMetrics(
        database_path()
    ) as metrics:
        daily = (
            metrics.daily_order_metrics()
        )

        inventory = (
            metrics
            .latest_inventory_summary()
        )

        funnel = (
            metrics
            .latest_funnel_metrics()
        )

        signals, signal_error = (
            load_signals(
                metrics
            )
        )

    full_series = (
        filled_daily_series(
            daily
        )
    )

    current_rows = (
        full_series[
            -days:
        ]
    )

    previous_end = max(
        0,
        len(full_series)
        - len(current_rows),
    )

    previous_start = max(
        0,
        previous_end
        - len(current_rows),
    )

    previous_rows = (
        full_series[
            previous_start:
            previous_end
        ]
    )

    current = (
        summarize_period(
            current_rows
        )
    )

    previous = None

    if (
        previous_rows
        and len(previous_rows)
        == len(current_rows)
    ):
        previous = (
            summarize_period(
                previous_rows
            )
        )

    changes = {
        "revenue":
            (
                percent_change(
                    Decimal(
                        str(
                            current[
                                "revenue"
                            ]
                        )
                    ),
                    Decimal(
                        str(
                            previous[
                                "revenue"
                            ]
                        )
                    ),
                )
                if previous
                else None
            ),

        "orders":
            (
                percent_change(
                    current[
                        "orders"
                    ],
                    previous[
                        "orders"
                    ],
                )
                if previous
                else None
            ),

        "aov":
            (
                percent_change(
                    Decimal(
                        str(
                            current[
                                "aov"
                            ]
                        )
                    ),
                    Decimal(
                        str(
                            previous[
                                "aov"
                            ]
                        )
                    ),
                )
                if previous
                else None
            ),

        "units_sold":
            (
                percent_change(
                    current[
                        "units_sold"
                    ],
                    previous[
                        "units_sold"
                    ],
                )
                if previous
                else None
            ),
    }

    return {
        "requested_days":
            days,

        "available_days":
            len(
                current_rows
            ),

        "current":
            current,

        "previous":
            previous,

        "changes_pct":
            changes,

        "trend":
            build_trend(
                full_series,
                days,
            ),

        "inventory":
            {
                "snapshot_at":
                    iso_value(
                        inventory[
                            "snapshot_at"
                        ]
                    ),

                "total_available":
                    inventory[
                        "total_available"
                    ],

                "out_of_stock_levels":
                    inventory[
                        "out_of_stock_levels"
                    ],

                "inventory_items":
                    inventory[
                        "inventory_items"
                    ],

                "locations":
                    inventory[
                        "locations"
                    ],
            },

        "funnel":
            (
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
                    ) in funnel.items()
                }
                if funnel
                else None
            ),

        "signals":
            signals,

        "signal_error":
            signal_error,
    }
