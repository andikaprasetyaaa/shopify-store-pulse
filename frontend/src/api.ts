import type {
    AnalystResponse,
    AnalystStatus,
    DataHealthResponse,
    ForecastMetric,
    ForecastResponse,
    FunnelResponse,
    InventoryResponse,
    OverviewResponse,
    SignalsResponse,
} from "./types";

/**
 * Single fetch helper for every dashboard route.
 *
 * The generic is a claim about the response, not a
 * check of it: FastAPI is the contract, and the
 * per-route wrappers below are the only places allowed
 * to make that claim, so a shape change has one
 * obvious place to be corrected.
 */
async function api<T>(url: string): Promise<T> {
    const response = await fetch(url, {
        cache: "no-store",
    });

    if (!response.ok) {
        const data: unknown = await response
            .json()
            .catch(() => ({}));

        const detail =
            typeof data === "object" &&
            data !== null &&
            "detail" in data
                ? String(
                      (data as { detail: unknown })
                          .detail,
                  )
                : "";

        throw new Error(
            detail || `HTTP ${response.status}`,
        );
    }

    return (await response.json()) as T;
}

export function fetchOverview(
    days: number,
): Promise<OverviewResponse> {
    return api<OverviewResponse>(
        `/api/overview?days=${days}`,
    );
}

export function fetchInventory(
    threshold: number,
    search: string,
    limit = 500,
): Promise<InventoryResponse> {
    const params = new URLSearchParams({
        threshold: String(threshold),
        search,
        limit: String(limit),
    });

    return api<InventoryResponse>(
        `/api/inventory?${params.toString()}`,
    );
}

export function fetchFunnel(): Promise<FunnelResponse> {
    return api<FunnelResponse>("/api/funnel");
}

export function fetchSignals(): Promise<SignalsResponse> {
    return api<SignalsResponse>("/api/signals");
}

export function fetchDataHealth(): Promise<DataHealthResponse> {
    return api<DataHealthResponse>(
        "/api/data-health",
    );
}

export function fetchForecast(
    metric: ForecastMetric,
    horizon: number,
): Promise<ForecastResponse> {
    const params = new URLSearchParams({
        metric,
        horizon: String(horizon),
        history_days: "30",
    });

    return api<ForecastResponse>(
        `/api/forecast?${params.toString()}`,
    );
}

export function fetchAnalystStatus(): Promise<AnalystStatus> {
    return api<AnalystStatus>(
        "/api/analyst/status",
    );
}

/**
 * Ask the analyst one question.
 *
 * A POST because the question is a body, and because
 * this is the one route in the app that costs money per
 * call - it should never be something a browser retries
 * or prefetches on its own.
 */
export async function askAnalyst(
    question: string,
    days: number,
    forecastMetric: ForecastMetric,
    forecastHorizon: number,
): Promise<AnalystResponse> {
    const response = await fetch("/api/analyst", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify({
            question,
            days,
            forecast_metric: forecastMetric,
            forecast_horizon: forecastHorizon,
        }),
    });

    if (!response.ok) {
        throw new Error(
            `HTTP ${response.status}`,
        );
    }

    return (await response.json()) as AnalystResponse;
}
