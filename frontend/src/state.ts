import type {
    ForecastMetric,
    PageName,
} from "./types";

/**
 * Filter state shared by the sidebar controls and the
 * pages that read them. One mutable object, same as
 * before: the dashboard has no routing and no history,
 * so there is nothing to keep in sync with a URL.
 */
export interface DashboardState {
    page: PageName;
    days: number;
    threshold: number;
    search: string;
    forecastMetric: ForecastMetric;
    forecastHorizon: number;
    analystQuestion: string;
}

export const state: DashboardState = {
    page: "overview",
    days: 30,
    threshold: 5,
    search: "",
    forecastMetric: "orders",
    forecastHorizon: 7,
    analystQuestion: "",
};

export const descriptions: Record<
    PageName,
    string
> = {
    overview:
        "Sales momentum, inventory health and active anomaly signals.",

    inventory:
        "Explore latest stock availability and identify low-stock variants.",

    funnel: "Monitor sessions, checkout progression and conversion.",

    signals:
        "Review downside anomalies against rolling baselines.",

    forecast:
        "Short-horizon demand forecast, scored against a seasonal naive benchmark.",

    analyst:
        "Ask Gemini to explain the figures above. It reads the dashboard's own numbers and never computes new ones.",

    data: "Inspect DuckDB synchronization and stored data coverage.",
};

/**
 * Element lookups that fail loudly.
 *
 * The old code assumed every id existed and would
 * silently do nothing if a markup edit renamed one.
 */
export function requireElement(
    id: string,
): HTMLElement {
    const element = document.getElementById(id);

    if (element === null) {
        throw new Error(
            `Missing element #${id} in index.html.`,
        );
    }

    return element;
}

export const content = requireElement("content");

export const controls = requireElement("controls");
