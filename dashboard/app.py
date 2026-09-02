from __future__ import annotations

import html
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# Project setup
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT_DIR),
    )


from analytics.anomalies import (
    AnomalyError,
    AnomalyResult,
    StorePulseAnomalyEngine,
)
from analytics.baseline import (
    BaselineError,
    StorePulseBaselines,
)
from analytics.metrics import (
    MetricsError,
    StorePulseMetrics,
)
from storage.database import (
    resolve_read_path,
)

# Shared with the API so both read the same numbers;
# this used to be a second copy that had already
# drifted from api/app.py.
from services.metadata import (
    collect_metadata as database_metadata,
)


# Prefer the serving copy published by the sync;
# DuckDB locks the live database while it writes.
DATABASE_PATH = resolve_read_path(ROOT_DIR)

CACHE_SECONDS = 30


# ============================================================
# Colors
# ============================================================

PURPLE = "#7C3AED"
BLUE = "#2563EB"
GREEN = "#10B981"
ORANGE = "#F59E0B"
RED = "#EF4444"
SLATE = "#64748B"


# ============================================================
# Streamlit page
# ============================================================

st.set_page_config(
    page_title="Store Pulse",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# Styles
# ============================================================

def inject_css() -> None:
    st.html(
        """
        <style>

        .block-container {
            max-width: 1480px;
            padding-top: 1.4rem;
            padding-bottom: 4rem;
        }

        [data-testid="stSidebar"] {
            border-right:
                1px solid
                rgba(128,128,128,.15);
        }

        [data-testid="stSidebar"]
        [role="radiogroup"] {
            gap: .25rem;
        }

        [data-testid="stSidebar"]
        [role="radiogroup"] label {
            padding:
                .55rem .6rem;

            border-radius:
                10px;
        }

        [data-testid="stMetric"] {
            padding:
                1.05rem 1.1rem;

            min-height:
                120px;

            border-radius:
                18px;

            border:
                1px solid
                rgba(128,128,128,.15);

            background:
                var(--secondary-background-color);

            box-shadow:
                0 8px 28px
                rgba(0,0,0,.035);
        }

        [data-testid="stMetricLabel"] {
            font-weight: 650;
            opacity: .65;
        }

        .sp-header {
            position: relative;
            overflow: hidden;

            padding:
                2rem 2.1rem;

            margin-bottom:
                1.25rem;

            border-radius:
                26px;

            border:
                1px solid
                rgba(124,58,237,.18);

            background:
                radial-gradient(
                    circle at 92% 0%,
                    rgba(37,99,235,.21),
                    transparent 34%
                ),
                radial-gradient(
                    circle at 5% 110%,
                    rgba(124,58,237,.20),
                    transparent 38%
                ),
                var(--secondary-background-color);
        }

        .sp-eyebrow {
            font-size:
                .72rem;

            font-weight:
                800;

            letter-spacing:
                .15em;

            text-transform:
                uppercase;

            color:
                #7C3AED;
        }

        .sp-page-title {
            margin-top:
                .45rem;

            font-size:
                clamp(
                    2rem,
                    4vw,
                    3.6rem
                );

            line-height:
                1;

            letter-spacing:
                -.05em;

            font-weight:
                850;
        }

        .sp-description {
            margin-top:
                .7rem;

            max-width:
                760px;

            font-size:
                .97rem;

            line-height:
                1.55;

            opacity:
                .68;
        }

        .sp-chips {
            display:
                flex;

            flex-wrap:
                wrap;

            gap:
                .5rem;

            margin-top:
                1rem;
        }

        .sp-chip {
            padding:
                .34rem .65rem;

            border-radius:
                999px;

            border:
                1px solid
                rgba(128,128,128,.17);

            background:
                rgba(128,128,128,.07);

            font-size:
                .75rem;

            font-weight:
                650;
        }

        .sp-signal {
            min-height:
                195px;

            padding:
                1rem;

            border-radius:
                18px;

            border:
                1px solid
                rgba(128,128,128,.15);

            background:
                var(--secondary-background-color);
        }

        .sp-signal-name {
            font-size:
                .72rem;

            font-weight:
                800;

            letter-spacing:
                .08em;

            text-transform:
                uppercase;

            opacity:
                .56;
        }

        .sp-signal-value {
            margin-top:
                .4rem;

            font-size:
                1.45rem;

            font-weight:
                820;
        }

        .sp-signal-meta {
            margin-top:
                .25rem;

            font-size:
                .78rem;

            opacity:
                .6;
        }

        .sp-signal-reason {
            margin-top:
                .75rem;

            font-size:
                .78rem;

            line-height:
                1.45;

            opacity:
                .7;
        }

        .sp-badge {
            display:
                inline-flex;

            margin-top:
                .65rem;

            padding:
                .24rem .55rem;

            border-radius:
                999px;

            font-size:
                .68rem;

            font-weight:
                800;
        }

        .sp-normal {
            color:
                #047857;

            background:
                rgba(16,185,129,.14);
        }

        .sp-warning {
            color:
                #B45309;

            background:
                rgba(245,158,11,.15);
        }

        .sp-critical {
            color:
                #B91C1C;

            background:
                rgba(239,68,68,.14);
        }

        .sp-waiting {
            color:
                #475569;

            background:
                rgba(100,116,139,.14);
        }

        .sp-data-note {
            padding:
                .8rem 1rem;

            margin:
                .3rem 0 1rem;

            border-radius:
                12px;

            border:
                1px solid
                rgba(128,128,128,.13);

            background:
                rgba(128,128,128,.05);

            font-size:
                .8rem;

            opacity:
                .7;
        }

        .sp-footer {
            margin-top:
                2rem;

            font-size:
                .75rem;

            line-height:
                1.5;

            opacity:
                .48;
        }

        </style>
        """
    )


# ============================================================
# Database metadata
# ============================================================



# ============================================================
# Load analytical data
# ============================================================

@st.cache_data(
    ttl=CACHE_SECONDS,
    show_spinner=False,
)
def load_data() -> dict[str, Any]:
    if not DATABASE_PATH.exists():
        raise MetricsError(
            "Production DuckDB "
            "does not exist."
        )

    anomalies: dict[
        str,
        AnomalyResult,
    ] = {}

    anomaly_error: str | None = None

    with StorePulseMetrics(
        DATABASE_PATH
    ) as metrics:
        daily = (
            metrics.daily_order_metrics()
        )

        inventory = (
            metrics.latest_inventory_summary()
        )

        inventory_variants = (
            metrics.latest_inventory_by_variant(
                limit=2000
            )
        )

        funnel = (
            metrics.latest_funnel_metrics()
        )

        if daily:
            try:
                baseline_engine = (
                    StorePulseBaselines(
                        metrics
                    )
                )

                anomaly_engine = (
                    StorePulseAnomalyEngine(
                        baseline_engine
                    )
                )

                anomalies = (
                    anomaly_engine
                    .analyze_order_metrics()
                )

            except (
                BaselineError,
                AnomalyError,
                ValueError,
            ) as exc:
                anomaly_error = str(
                    exc
                )

    return {
        "daily":
            daily,

        "inventory":
            inventory,

        "inventory_variants":
            inventory_variants,

        "funnel":
            funnel,

        "anomalies":
            anomalies,

        "anomaly_error":
            anomaly_error,

        "metadata":
            database_metadata(),
    }


# ============================================================
# Formatting
# ============================================================

def format_money(
    value: Any,
    currency: str | None,
) -> str:
    if value is None:
        return "N/A"

    number = Decimal(
        str(value)
    )

    suffix = (
        f" {currency}"
        if currency
        else ""
    )

    return (
        f"{number:,.2f}"
        f"{suffix}"
    )


def format_int(
    value: Any,
) -> str:
    if value is None:
        return "N/A"

    return (
        f"{int(float(value)):,}"
    )


def format_pct(
    value: Any,
) -> str:
    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:.2f}%"
    )


def format_time(
    value: Any,
) -> str:
    if value is None:
        return "Not available"

    if isinstance(
        value,
        datetime,
    ):
        return value.strftime(
            "%d %b %Y %H:%M"
        )

    return str(value)


def delta_text(
    current: Any,
    previous: Any,
) -> str | None:
    current_decimal = Decimal(
        str(current)
    )

    previous_decimal = Decimal(
        str(previous)
    )

    if previous_decimal == 0:
        return None

    delta = (
        (
            current_decimal
            - previous_decimal
        )
        / previous_decimal
        * Decimal("100")
    )

    return (
        f"{delta:+.1f}% "
        "vs previous period"
    )


# ============================================================
# Daily dataframe
# ============================================================

def build_daily_frame(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(
        rows
    )

    frame["day"] = pd.to_datetime(
        frame["day"]
    )

    for column in [
        "revenue",
        "orders",
        "aov",
        "units_sold",
    ]:
        frame[column] = (
            pd.to_numeric(
                frame[column],
                errors="coerce",
            )
            .fillna(0)
        )

    frame = (
        frame
        .sort_values("day")
        .set_index("day")
    )

    full_index = pd.date_range(
        start=frame.index.min(),
        end=frame.index.max(),
        freq="D",
    )

    frame = frame.reindex(
        full_index,
        fill_value=0,
    )

    frame.index.name = "day"

    frame = frame.reset_index()

    frame["baseline_7d"] = (
        frame["revenue"]
        .shift(1)
        .rolling(
            window=7,
            min_periods=7,
        )
        .mean()
    )

    return frame


# ============================================================
# Reporting-window calculation
# ============================================================

def summarize_window(
    frame: pd.DataFrame,
    days: int,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "current": None,
            "previous": None,
            "available_days": 0,
        }

    current = frame.tail(
        days
    ).copy()

    remaining = frame.iloc[
        : max(
            0,
            len(frame) - len(current),
        )
    ]

    previous = remaining.tail(
        days
    ).copy()

    return {
        "current":
            calculate_period(
                current
            ),

        "previous":
            (
                calculate_period(
                    previous
                )
                if not previous.empty
                else None
            ),

        "available_days":
            len(current),
    }


def calculate_period(
    frame: pd.DataFrame,
) -> dict[str, Any]:
    revenue = Decimal(
        str(
            round(
                float(
                    frame[
                        "revenue"
                    ].sum()
                ),
                2,
            )
        )
    )

    orders = int(
        frame[
            "orders"
        ].sum()
    )

    units = int(
        frame[
            "units_sold"
        ].sum()
    )

    aov = (
        revenue
        / Decimal(orders)
        if orders
        else Decimal("0")
    )

    return {
        "revenue":
            revenue,

        "orders":
            orders,

        "units_sold":
            units,

        "aov":
            aov,

        "start":
            frame[
                "day"
            ].min(),

        "end":
            frame[
                "day"
            ].max(),
    }


# ============================================================
# Inventory dataframe
# ============================================================

def build_inventory_frame(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(
        rows
    )

    frame["sku"] = (
        frame["sku"]
        .fillna("-")
    )

    frame["available"] = (
        pd.to_numeric(
            frame["available"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    frame["locations"] = (
        pd.to_numeric(
            frame["locations"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    return (
        frame
        .sort_values(
            [
                "available",
                "product_title",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# Charts
# ============================================================

def revenue_chart(
    frame: pd.DataFrame,
) -> go.Figure:
    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=frame["day"],
            y=frame["revenue"],

            mode="lines+markers",

            name="Revenue",

            line={
                "color":
                    PURPLE,

                "width":
                    3,
            },

            marker={
                "size":
                    6,
            },

            hovertemplate=(
                "%{x|%d %b %Y}"
                "<br>"
                "Revenue: %{y:,.2f}"
                "<extra></extra>"
            ),
        )
    )

    figure.add_trace(
        go.Scatter(
            x=frame["day"],

            y=frame[
                "baseline_7d"
            ],

            mode="lines",

            name="Prior 7d average",

            line={
                "color":
                    SLATE,

                "width":
                    2,

                "dash":
                    "dot",
            },

            hovertemplate=(
                "%{x|%d %b %Y}"
                "<br>"
                "7d baseline: %{y:,.2f}"
                "<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        height=400,

        margin={
            "l": 8,
            "r": 8,
            "t": 20,
            "b": 8,
        },

        hovermode="x unified",

        xaxis_title=None,
        yaxis_title=None,

        paper_bgcolor=(
            "rgba(0,0,0,0)"
        ),

        plot_bgcolor=(
            "rgba(0,0,0,0)"
        ),

        legend={
            "orientation":
                "h",
        },
    )

    figure.update_xaxes(
        showgrid=False
    )

    figure.update_yaxes(
        zeroline=False,

        gridcolor=(
            "rgba(128,128,128,.10)"
        ),
    )

    return figure


def orders_chart(
    frame: pd.DataFrame,
) -> go.Figure:
    figure = go.Figure(
        go.Bar(
            x=frame["day"],
            y=frame["orders"],

            marker_color=BLUE,

            hovertemplate=(
                "%{x|%d %b %Y}"
                "<br>"
                "Orders: %{y:,.0f}"
                "<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        height=400,

        margin={
            "l": 8,
            "r": 8,
            "t": 20,
            "b": 8,
        },

        showlegend=False,

        xaxis_title=None,
        yaxis_title=None,

        paper_bgcolor=(
            "rgba(0,0,0,0)"
        ),

        plot_bgcolor=(
            "rgba(0,0,0,0)"
        ),
    )

    figure.update_xaxes(
        showgrid=False
    )

    figure.update_yaxes(
        gridcolor=(
            "rgba(128,128,128,.10)"
        ),
    )

    return figure


def inventory_chart(
    frame: pd.DataFrame,
) -> go.Figure:
    selected = (
        frame.head(20)
        .copy()
    )

    figure = go.Figure(
        go.Bar(
            x=selected[
                "available"
            ],

            y=selected[
                "sku"
            ],

            orientation="h",

            marker_color=ORANGE,

            customdata=selected[
                [
                    "product_title",
                    "locations",
                ]
            ],

            hovertemplate=(
                "%{customdata[0]}"
                "<br>"
                "Available: %{x}"
                "<br>"
                "Locations: "
                "%{customdata[1]}"
                "<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        height=520,

        margin={
            "l": 8,
            "r": 8,
            "t": 20,
            "b": 8,
        },

        showlegend=False,

        xaxis_title=(
            "Available units"
        ),

        yaxis_title=None,

        paper_bgcolor=(
            "rgba(0,0,0,0)"
        ),

        plot_bgcolor=(
            "rgba(0,0,0,0)"
        ),
    )

    figure.update_yaxes(
        autorange="reversed"
    )

    return figure


def funnel_chart(
    funnel: dict[str, Any],
) -> go.Figure:
    values = [
        funnel.get(
            "sessions"
        ) or 0,

        funnel.get(
            "sessions_with_cart_additions"
        ) or 0,

        funnel.get(
            "sessions_that_reached_checkout"
        ) or 0,

        funnel.get(
            "sessions_that_completed_checkout"
        ) or 0,
    ]

    figure = go.Figure(
        go.Funnel(
            y=[
                "Sessions",
                "Cart additions",
                "Reached checkout",
                "Completed checkout",
            ],

            x=values,

            textinfo=(
                "value+percent initial"
            ),

            marker={
                "color": [
                    PURPLE,
                    BLUE,
                    GREEN,
                    ORANGE,
                ]
            },
        )
    )

    figure.update_layout(
        height=440,

        margin={
            "l": 8,
            "r": 8,
            "t": 20,
            "b": 8,
        },

        paper_bgcolor=(
            "rgba(0,0,0,0)"
        ),

        plot_bgcolor=(
            "rgba(0,0,0,0)"
        ),
    )

    return figure


# ============================================================
# Hero
# ============================================================

PAGE_DESCRIPTIONS = {
    "Overview":
        (
            "Executive view of sales momentum, "
            "inventory health and active signals."
        ),

    "Inventory":
        (
            "Explore latest stock availability "
            "and identify low-stock variants."
        ),

    "Funnel":
        (
            "Monitor online-store sessions, "
            "checkout progression and conversion."
        ),

    "Signals":
        (
            "Review baseline deviations and "
            "downside anomaly alerts."
        ),

    "Data":
        (
            "Inspect DuckDB synchronization "
            "health and stored dataset coverage."
        ),
}


def render_header(
    page: str,
    data: dict[str, Any],
) -> None:
    metadata = (
        data["metadata"]
    )

    order_start = (
        metadata[
            "order_start"
        ]
        or "N/A"
    )

    order_end = (
        metadata[
            "order_end"
        ]
        or "N/A"
    )

    inventory_sync = (
        format_time(
            metadata[
                "inventory_synced_at"
            ]
        )
    )

    st.html(
        f"""
        <div class="sp-header">

            <div class="sp-eyebrow">
                Shopify Store Pulse
            </div>

            <div class="sp-page-title">
                {html.escape(page)}
            </div>

            <div class="sp-description">
                {
                    html.escape(
                        PAGE_DESCRIPTIONS[
                            page
                        ]
                    )
                }
            </div>

            <div class="sp-chips">

                <span class="sp-chip">
                    Read-only
                </span>

                <span class="sp-chip">
                    Orders:
                    {
                        html.escape(
                            str(order_start)
                        )
                    }
                    →
                    {
                        html.escape(
                            str(order_end)
                        )
                    }
                </span>

                <span class="sp-chip">
                    Inventory synced:
                    {
                        html.escape(
                            inventory_sync
                        )
                    }
                </span>

            </div>

        </div>
        """
    )


# ============================================================
# Sidebar navigation
# ============================================================

def render_sidebar(
    data: dict[str, Any],
) -> dict[str, Any]:
    metadata = (
        data["metadata"]
    )

    st.sidebar.title(
        "Store Pulse"
    )

    st.sidebar.caption(
        "Commerce intelligence"
    )

    page = st.sidebar.radio(
        "Navigation",

        options=[
            "Overview",
            "Inventory",
            "Funnel",
            "Signals",
            "Data",
        ],

        key="navigation_page",

        label_visibility="collapsed",

        width="stretch",
    )

    controls: dict[str, Any] = {
        "page":
            page,

        "reporting_days":
            30,

        "stock_threshold":
            5,

        "inventory_search":
            "",
    }

    st.sidebar.divider()

    if page == "Overview":
        controls[
            "reporting_days"
        ] = st.sidebar.selectbox(
            "Reporting window",

            options=[
                7,
                14,
                30,
                60,
            ],

            index=2,

            key="reporting_window",

            format_func=(
                lambda value:
                    f"Last {value} days"
            ),
        )

    elif page == "Inventory":
        controls[
            "stock_threshold"
        ] = st.sidebar.slider(
            "Low-stock threshold",

            min_value=0,
            max_value=100,
            value=5,
            step=1,

            key=(
                "inventory_threshold"
            ),
        )

        controls[
            "inventory_search"
        ] = st.sidebar.text_input(
            "Search SKU / Product",
            value="",
            key=(
                "inventory_search"
            ),
        )

    st.sidebar.divider()

    if st.sidebar.button(
        "Refresh dashboard",
        width="stretch",
    ):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.caption(
        "Refresh reloads DuckDB only."
    )

    st.sidebar.divider()

    st.sidebar.markdown(
        "**Data coverage**"
    )

    st.sidebar.caption(
        "Orders: "
        f"{metadata['counts']['orders']:,}"
    )

    st.sidebar.caption(
        "Variants: "
        f"{metadata['counts']['product_variants']:,}"
    )

    st.sidebar.caption(
        "Inventory items: "
        f"{metadata['counts']['inventory_items']:,}"
    )

    st.sidebar.caption(
        "Order range: "
        f"{metadata['order_start']} "
        "→ "
        f"{metadata['order_end']}"
    )

    st.sidebar.divider()

    st.sidebar.markdown(
        "**Latest sync**"
    )

    st.sidebar.caption(
        "Orders: "
        + format_time(
            metadata[
                "orders_synced_at"
            ]
        )
    )

    st.sidebar.caption(
        "Inventory: "
        + format_time(
            metadata[
                "inventory_synced_at"
            ]
        )
    )

    st.sidebar.caption(
        "ShopifyQL: "
        + format_time(
            metadata[
                "analytics_synced_at"
            ]
        )
    )

    return controls


# ============================================================
# Anomaly cards
# ============================================================

def severity_class(
    severity: str,
) -> str:
    return {
        "NORMAL":
            "sp-normal",

        "WARNING":
            "sp-warning",

        "CRITICAL":
            "sp-critical",

        "INSUFFICIENT_DATA":
            "sp-waiting",
    }.get(
        severity,
        "sp-waiting",
    )


def render_signal_card(
    result: AnomalyResult,
) -> None:
    metric = (
        result["metric"]
    )

    currency = (
        result[
            "currency_code"
        ]
    )

    if metric in {
        "revenue",
        "aov",
    }:
        current = format_money(
            result[
                "current_value"
            ],
            currency,
        )

        baseline = format_money(
            result[
                "baseline_value"
            ],
            currency,
        )

    else:
        current = format_int(
            result[
                "current_value"
            ]
        )

        baseline = format_int(
            result[
                "baseline_value"
            ]
        )

    deviation = (
        result[
            "deviation_pct"
        ]
    )

    deviation_text = (
        f"{deviation:+.2f}%"
        if deviation is not None
        else "N/A"
    )

    severity = (
        result[
            "severity"
        ]
    )

    title = (
        metric
        .replace(
            "_",
            " ",
        )
        .title()
    )

    st.html(
        f"""
        <div class="sp-signal">

            <div class="sp-signal-name">
                {html.escape(title)}
            </div>

            <div class="sp-signal-value">
                {html.escape(current)}
            </div>

            <div class="sp-signal-meta">
                Prior 7d:
                {html.escape(baseline)}
                ·
                {html.escape(deviation_text)}
            </div>

            <span class="
                sp-badge
                {severity_class(severity)}
            ">
                {html.escape(severity)}
            </span>

            <div class="sp-signal-reason">
                {
                    html.escape(
                        result[
                            "reason"
                        ]
                    )
                }
            </div>

        </div>
        """
    )


# ============================================================
# Overview page
# ============================================================

def render_overview(
    data: dict[str, Any],
    days: int,
) -> None:
    frame = build_daily_frame(
        data["daily"]
    )

    if frame.empty:
        st.info(
            "No order history "
            "is available."
        )
        return

    window = summarize_window(
        frame,
        days,
    )

    current = window[
        "current"
    ]

    previous = window[
        "previous"
    ]

    available_days = int(
        window[
            "available_days"
        ]
    )

    currency = (
        data["daily"][-1]
        .get(
            "currency_code"
        )
    )

    st.html(
        f"""
        <div class="sp-data-note">
            Reporting window requested:
            <strong>
                {days} days
            </strong>.
            Available in DuckDB:
            <strong>
                {available_days} days
            </strong>.
        </div>
        """
    )

    columns = st.columns(
        4
    )

    revenue_delta = (
        delta_text(
            current["revenue"],
            previous["revenue"],
        )
        if previous
        else None
    )

    orders_delta = (
        delta_text(
            current["orders"],
            previous["orders"],
        )
        if previous
        else None
    )

    aov_delta = (
        delta_text(
            current["aov"],
            previous["aov"],
        )
        if previous
        else None
    )

    units_delta = (
        delta_text(
            current[
                "units_sold"
            ],
            previous[
                "units_sold"
            ],
        )
        if previous
        else None
    )

    with columns[0]:
        st.metric(
            f"Revenue · {days}d",

            format_money(
                current[
                    "revenue"
                ],
                currency,
            ),

            delta=revenue_delta,
        )

    with columns[1]:
        st.metric(
            f"Orders · {days}d",

            format_int(
                current[
                    "orders"
                ]
            ),

            delta=orders_delta,
        )

    with columns[2]:
        st.metric(
            f"AOV · {days}d",

            format_money(
                current[
                    "aov"
                ],
                currency,
            ),

            delta=aov_delta,
        )

    with columns[3]:
        st.metric(
            f"Units sold · {days}d",

            format_int(
                current[
                    "units_sold"
                ]
            ),

            delta=units_delta,
        )

    inventory = (
        data[
            "inventory"
        ]
    )

    funnel = (
        data[
            "funnel"
        ]
    )

    st.markdown(
        "### Store health"
    )

    columns = st.columns(
        3
    )

    with columns[0]:
        st.metric(
            "Available stock",

            format_int(
                inventory[
                    "total_available"
                ]
            ),
        )

    with columns[1]:
        st.metric(
            "Out-of-stock levels",

            format_int(
                inventory[
                    "out_of_stock_levels"
                ]
            ),
        )

    with columns[2]:
        st.metric(
            "Conversion rate",

            format_pct(
                funnel[
                    "conversion_rate"
                ]
                if funnel
                else None
            ),
        )

    selected_frame = (
        frame.tail(
            days
        )
    )

    left, right = st.columns(
        2
    )

    with left:
        st.markdown(
            "### Revenue momentum"
        )

        st.plotly_chart(
            revenue_chart(
                selected_frame
            ),

            width="stretch",

            theme="streamlit",

            config={
                "displayModeBar":
                    False,
            },
        )

    with right:
        st.markdown(
            "### Order volume"
        )

        st.plotly_chart(
            orders_chart(
                selected_frame
            ),

            width="stretch",

            theme="streamlit",

            config={
                "displayModeBar":
                    False,
            },
        )

    st.markdown(
        "### Signals"
    )

    anomalies = (
        data[
            "anomalies"
        ]
    )

    if anomalies:
        columns = st.columns(
            4
        )

        names = [
            "revenue",
            "orders",
            "aov",
            "units_sold",
        ]

        for index, metric in (
            enumerate(names)
        ):
            with columns[index]:
                render_signal_card(
                    anomalies[
                        metric
                    ]
                )

    elif data[
        "anomaly_error"
    ]:
        st.warning(
            data[
                "anomaly_error"
            ]
        )


# ============================================================
# Inventory page
# ============================================================

def render_inventory(
    data: dict[str, Any],
    threshold: int,
    search: str,
) -> None:
    inventory = (
        data[
            "inventory"
        ]
    )

    columns = st.columns(
        4
    )

    with columns[0]:
        st.metric(
            "Available units",

            format_int(
                inventory[
                    "total_available"
                ]
            ),
        )

    with columns[1]:
        st.metric(
            "Inventory items",

            format_int(
                inventory[
                    "inventory_items"
                ]
            ),
        )

    with columns[2]:
        st.metric(
            "Locations",

            format_int(
                inventory[
                    "locations"
                ]
            ),
        )

    with columns[3]:
        st.metric(
            "Out-of-stock levels",

            format_int(
                inventory[
                    "out_of_stock_levels"
                ]
            ),
        )

    frame = build_inventory_frame(
        data[
            "inventory_variants"
        ]
    )

    if frame.empty:
        st.info(
            "No inventory data."
        )
        return

    if search.strip():
        term = (
            search.strip()
            .lower()
        )

        frame = frame[
            frame[
                "product_title"
            ]
            .str.lower()
            .str.contains(
                term,
                na=False,
            )
            |
            frame[
                "sku"
            ]
            .str.lower()
            .str.contains(
                term,
                na=False,
            )
        ]

    low_stock = frame[
        frame["available"]
        <= threshold
    ].copy()

    st.markdown(
        f"### Low stock ≤ "
        f"{threshold} units"
    )

    left, right = st.columns(
        [
            1,
            1.15,
        ]
    )

    with left:
        if low_stock.empty:
            st.success(
                "No matching variants "
                "are below the threshold."
            )

            chart_frame = (
                frame.head(20)
            )

        else:
            chart_frame = (
                low_stock.head(20)
            )

        if not chart_frame.empty:
            st.plotly_chart(
                inventory_chart(
                    chart_frame
                ),

                width="stretch",

                theme="streamlit",

                config={
                    "displayModeBar":
                        False,
                },
            )

    with right:
        table = (
            low_stock
            if not low_stock.empty
            else frame
        )

        table = table[
            [
                "product_title",
                "sku",
                "available",
                "locations",
            ]
        ].head(
            250
        ).copy()

        table.columns = [
            "Product",
            "SKU",
            "Available",
            "Locations",
        ]

        st.dataframe(
            table,

            width="stretch",

            hide_index=True,
        )


# ============================================================
# Funnel page
# ============================================================

def render_funnel(
    data: dict[str, Any],
) -> None:
    funnel = (
        data[
            "funnel"
        ]
    )

    if funnel is None:
        st.info(
            "ShopifyQL funnel data "
            "has not been stored yet."
        )
        return

    columns = st.columns(
        4
    )

    with columns[0]:
        st.metric(
            "Sessions",

            format_int(
                funnel[
                    "sessions"
                ]
            ),
        )

    with columns[1]:
        st.metric(
            "Visitors",

            format_int(
                funnel[
                    "online_store_visitors"
                ]
            ),
        )

    with columns[2]:
        st.metric(
            "Conversion",

            format_pct(
                funnel[
                    "conversion_rate"
                ]
            ),
        )

    with columns[3]:
        st.metric(
            "Completed checkout",

            format_int(
                funnel[
                    "sessions_that_completed_checkout"
                ]
            ),
        )

    left, right = st.columns(
        [
            1.5,
            .5,
        ]
    )

    with left:
        st.plotly_chart(
            funnel_chart(
                funnel
            ),

            width="stretch",

            theme="streamlit",

            config={
                "displayModeBar":
                    False,
            },
        )

    with right:
        st.markdown(
            "### Snapshot"
        )

        st.write(
            "Day:",
            funnel[
                "day"
            ]
            or "N/A",
        )

        st.write(
            "Cart additions:",
            format_int(
                funnel[
                    "sessions_with_cart_additions"
                ]
            ),
        )

        st.write(
            "Reached checkout:",
            format_int(
                funnel[
                    "sessions_that_reached_checkout"
                ]
            ),
        )

        st.write(
            "Completed:",
            format_int(
                funnel[
                    "sessions_that_completed_checkout"
                ]
            ),
        )


# ============================================================
# Signals page
# ============================================================

def render_signals(
    data: dict[str, Any],
) -> None:
    anomalies = (
        data[
            "anomalies"
        ]
    )

    if not anomalies:
        st.info(
            data[
                "anomaly_error"
            ]
            or
            "No anomaly signals available."
        )
        return

    columns = st.columns(
        4
    )

    names = [
        "revenue",
        "orders",
        "aov",
        "units_sold",
    ]

    for index, metric in (
        enumerate(names)
    ):
        with columns[index]:
            render_signal_card(
                anomalies[
                    metric
                ]
            )

    st.markdown(
        "### Signal details"
    )

    rows = []

    for metric in names:
        result = (
            anomalies[
                metric
            ]
        )

        rows.append(
            {
                "Metric":
                    metric
                    .replace(
                        "_",
                        " ",
                    )
                    .title(),

                "Severity":
                    result[
                        "severity"
                    ],

                "Current":
                    float(
                        result[
                            "current_value"
                        ]
                    ),

                "7d baseline":
                    (
                        float(
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

                "Deviation %":
                    (
                        float(
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

                "Reason":
                    result[
                        "reason"
                    ],
            }
        )

    st.dataframe(
        pd.DataFrame(
            rows
        ),

        width="stretch",

        hide_index=True,
    )

    critical = [
        result
        for result in anomalies.values()
        if result[
            "severity"
        ] == "CRITICAL"
    ]

    warning = [
        result
        for result in anomalies.values()
        if result[
            "severity"
        ] == "WARNING"
    ]

    for result in critical:
        st.error(
            result[
                "reason"
            ]
        )

    for result in warning:
        st.warning(
            result[
                "reason"
            ]
        )

    if (
        not critical
        and not warning
    ):
        st.success(
            "No active warning or "
            "critical downside signals."
        )


# ============================================================
# Data page
# ============================================================

def render_data_health(
    data: dict[str, Any],
) -> None:
    metadata = (
        data[
            "metadata"
        ]
    )

    counts = (
        metadata[
            "counts"
        ]
    )

    st.markdown(
        "### Production DuckDB"
    )

    st.code(
        str(
            DATABASE_PATH
        ),
        language=None,
    )

    sync_rows = [
        {
            "Dataset":
                "Orders",

            "Last sync":
                format_time(
                    metadata[
                        "orders_synced_at"
                    ]
                ),
        },

        {
            "Dataset":
                "Inventory",

            "Last sync":
                format_time(
                    metadata[
                        "inventory_synced_at"
                    ]
                ),
        },

        {
            "Dataset":
                "ShopifyQL",

            "Last sync":
                format_time(
                    metadata[
                        "analytics_synced_at"
                    ]
                ),
        },
    ]

    st.markdown(
        "### Synchronization"
    )

    st.dataframe(
        pd.DataFrame(
            sync_rows
        ),

        width="stretch",

        hide_index=True,
    )

    st.markdown(
        "### Stored rows"
    )

    count_rows = [
        {
            "Table":
                table,

            "Rows":
                count,
        }
        for table, count
        in counts.items()
    ]

    st.dataframe(
        pd.DataFrame(
            count_rows
        ),

        width="stretch",

        hide_index=True,
    )

    st.markdown(
        "### Data coverage"
    )

    col1, col2, col3 = (
        st.columns(3)
    )

    with col1:
        st.metric(
            "Stored orders",
            f"{counts['orders']:,}",
        )

    with col2:
        st.metric(
            "Product variants",
            f"{counts['product_variants']:,}",
        )

    with col3:
        st.metric(
            "Latest inventory items",
            (
                f"{metadata['latest_inventory_items']:,}"
            ),
        )

    if counts[
        "orders"
    ] <= 20:
        st.warning(
            "The production database "
            "contains 20 or fewer orders. "
            "This looks like smoke-test data. "
            "Run the production sync."
        )

    if (
        metadata[
            "order_start"
        ]
        ==
        metadata[
            "order_end"
        ]
        and counts[
            "orders"
        ] > 1
    ):
        st.warning(
            "All stored orders currently "
            "fall on one calendar day. "
            "Reporting-window selections "
            "will therefore look similar."
        )

    st.markdown(
        "### Production sync command"
    )

    st.code(
        "python3 -m scripts.sync_data "
        "--skip-products",
        language=None,
    )


# ============================================================
# Main
# ============================================================

def main() -> None:
    inject_css()

    if not DATABASE_PATH.exists():
        st.error(
            "Production database "
            "does not exist."
        )

        st.code(
            "python3 -m scripts.sync_data "
            "--reset",
            language=None,
        )

        st.stop()

    try:
        data = load_data()

    except (
        MetricsError,
        duckdb.Error,
    ) as exc:
        st.error(
            "Dashboard database error"
        )

        st.code(
            str(exc),
            language=None,
        )

        st.stop()

    controls = render_sidebar(
        data
    )

    page = controls[
        "page"
    ]

    render_header(
        page,
        data,
    )

    if page == "Overview":
        render_overview(
            data,
            int(
                controls[
                    "reporting_days"
                ]
            ),
        )

    elif page == "Inventory":
        render_inventory(
            data,

            int(
                controls[
                    "stock_threshold"
                ]
            ),

            str(
                controls[
                    "inventory_search"
                ]
            ),
        )

    elif page == "Funnel":
        render_funnel(
            data
        )

    elif page == "Signals":
        render_signals(
            data
        )

    elif page == "Data":
        render_data_health(
            data
        )

    st.html(
        """
        <div class="sp-footer">

            Store Pulse reads the local
            DuckDB analytical database only.

            Shopify Admin API access remains
            isolated in the collector and
            synchronization layer.

        </div>
        """
    )


if __name__ == "__main__":
    main()