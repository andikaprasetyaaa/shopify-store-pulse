/**
 * Shapes returned by the FastAPI routes in
 * api/routers/dashboard.py and api/routers/system.py.
 *
 * These were written against real responses from a
 * populated database, so the nullable fields here are
 * the ones the Python services can actually emit:
 * `previous` and `funnel` are null on a short history,
 * every `changes_pct` entry is null without a previous
 * period, `baseline_7d` is null for the first days of a
 * window, and `accuracy` is null when the history is
 * too short to backtest.
 */

export type PageName =
    | "overview"
    | "inventory"
    | "funnel"
    | "signals"
    | "forecast"
    | "analyst"
    | "data";

export type Severity =
    | "NORMAL"
    | "WARNING"
    | "CRITICAL";

export type MetricName =
    | "revenue"
    | "orders"
    | "aov"
    | "units_sold";

export type ForecastMetric =
    | "orders"
    | "revenue";

// ============================================================
// /api/overview
// ============================================================

export interface PeriodTotals {
    revenue: number;
    orders: number;
    aov: number;
    units_sold: number;
    currency_code: string;
    start: string | null;
    end: string | null;
}

export interface TrendRow {
    day: string;
    revenue: number;
    orders: number;
    aov: number;
    units_sold: number;
    baseline_7d: number | null;
}

export interface InventoryHeadline {
    snapshot_at: string | null;
    total_available: number;
    out_of_stock_levels: number;
    inventory_items: number;
    locations: number;
}

export interface FunnelData {
    snapshot_at: string | null;
    day: string;
    sessions: number;
    online_store_visitors: number;
    conversion_rate: number;
    sessions_with_cart_additions: number;
    sessions_that_reached_checkout: number;
    sessions_that_completed_checkout: number;
}

export interface Signal {
    metric: MetricName;
    as_of_day: string;
    current_value: number;
    baseline_name: string;
    baseline_value: number | null;
    deviation_pct: number | null;
    direction: "UP" | "DOWN" | "FLAT";
    severity: Severity;
    reason: string;
    currency_code: string;
}

export type SignalMap = Partial<
    Record<MetricName, Signal>
>;

export type ChangesPct = Record<
    keyof Pick<
        PeriodTotals,
        "revenue" | "orders" | "aov" | "units_sold"
    >,
    number | null
>;

export interface OverviewResponse {
    requested_days: number;
    available_days: number;
    current: PeriodTotals;
    previous: PeriodTotals | null;
    changes_pct: ChangesPct;
    trend: TrendRow[];
    inventory: InventoryHeadline;
    funnel: FunnelData | null;
    signals: SignalMap;
    signal_error: string | null;
}

// ============================================================
// /api/inventory
// ============================================================

export interface InventorySummary {
    snapshot_at: string | null;
    inventory_items: number;
    inventory_levels: number;
    locations: number;
    tracked_items: number;
    total_available: number;
    out_of_stock_levels: number;
}

export interface InventoryItem {
    variant_id: string;
    product_id: string;
    product_title: string;
    sku: string | null;
    available: number;
    locations: number;
}

export interface InventoryResponse {
    summary: InventorySummary;
    threshold: number;
    search: string;
    returned: number;
    items: InventoryItem[];
}

// ============================================================
// /api/funnel
// ============================================================

export interface FunnelResponse {
    available: boolean;
    data: FunnelData | null;
}

// ============================================================
// /api/signals
// ============================================================

export interface SignalsResponse {
    signals: SignalMap;
    error: string | null;
}

// ============================================================
// /api/data-health
// ============================================================

export interface DataHealthResponse {
    database: string;
    counts: Record<string, number>;
    order_start: string | null;
    order_end: string | null;
    orders_synced_at: string | null;
    inventory_synced_at: string | null;
    analytics_synced_at: string | null;
    latest_inventory_items: number;
}

// ============================================================
// /api/forecast
// ============================================================

export interface HistoryPoint {
    day: string;
    value: number;
}

export interface ForecastPoint {
    day: string;
    predicted: number;
    lower: number;
    upper: number;
}

/**
 * Backtest scores for the deployed model, so the chart
 * can show the forecast next to its own track record
 * rather than as a bare number.
 */
export interface ForecastAccuracy {
    model_mape: number;
    benchmark: string;
    benchmark_mape: number;
    folds: number;
}

export interface ForecastResponse {
    metric: ForecastMetric;
    model: string | null;
    history: HistoryPoint[];
    forecast: ForecastPoint[];
    accuracy: ForecastAccuracy | null;
    error: string | null;
}

// ============================================================
// /api/analyst
// ============================================================

export interface AnalystStatus {
    configured: boolean;
    model: string | null;
    error: string | null;
}

export interface AnalystContextSummary {
    reporting_window_days: number;
    forecast_metric: ForecastMetric;
    forecast_horizon: number;
    order_start: string | null;
    order_end: string | null;
}

export interface AnalystResponse {
    question: string;
    /** Null whenever `error` is set. */
    answer: string | null;
    model: string | null;
    cached: boolean;
    error: string | null;
    context_summary?: AnalystContextSummary;
}
