import { escapeHtml } from "./format";
import {
    controls,
    requireElement,
    state,
} from "./state";
import type { ForecastMetric } from "./types";

/**
 * Sidebar filters for the current page.
 *
 * `onChange` is passed in rather than imported so this
 * module does not have to reach back into main.ts and
 * create an import cycle.
 */
export function renderControls(
    onChange: () => void,
): void {
    // The analyst reasons over the same reporting window
    // the overview renders, and that window changes what
    // is sent to the model - so it gets the same control
    // rather than "no page-specific filters".
    if (
        state.page === "overview" ||
        state.page === "analyst"
    ) {
        renderOverviewControls(onChange);

        return;
    }

    if (state.page === "inventory") {
        renderInventoryControls(onChange);

        return;
    }

    if (state.page === "forecast") {
        renderForecastControls(onChange);

        return;
    }

    controls.innerHTML = `
        <div class="sidebar-small">
            No page-specific filters.
        </div>
    `;
}

function renderOverviewControls(
    onChange: () => void,
): void {
    controls.innerHTML = `
        <label class="sidebar-label">
            Reporting window
        </label>

        <select
            id="days"
            class="control"
        >
            <option value="7">
                Last 7 days
            </option>

            <option value="14">
                Last 14 days
            </option>

            <option value="30">
                Last 30 days
            </option>

            <option value="60">
                Last 60 days
            </option>
        </select>
    `;

    const days = requireElement(
        "days",
    ) as HTMLSelectElement;

    days.value = String(state.days);

    days.addEventListener("change", () => {
        state.days = Number(days.value);

        onChange();
    });
}

function renderInventoryControls(
    onChange: () => void,
): void {
    controls.innerHTML = `
        <label class="sidebar-label">
            Low-stock threshold
        </label>

        <input
            id="threshold"
            class="control"
            type="number"
            min="0"
            value="${state.threshold}"
        >

        <label class="sidebar-label">
            Search product / SKU
        </label>

        <input
            id="search"
            class="control"
            type="text"
            value="${escapeHtml(state.search)}"
            placeholder="e.g. sweater"
        >
    `;

    const threshold = requireElement(
        "threshold",
    ) as HTMLInputElement;

    const search = requireElement(
        "search",
    ) as HTMLInputElement;

    threshold.addEventListener("change", () => {
        state.threshold = Math.max(
            0,
            Number(threshold.value),
        );

        onChange();
    });

    let timer: number | undefined;

    search.addEventListener("input", () => {
        clearTimeout(timer);

        timer = window.setTimeout(() => {
            state.search = search.value;

            onChange();
        }, 350);
    });
}

/**
 * The horizon stops at 14 because that is the API's
 * cap, and the backtest shows the model losing its
 * edge over the benchmark well before the end of that
 * range.
 */
function renderForecastControls(
    onChange: () => void,
): void {
    controls.innerHTML = `
        <label class="sidebar-label">
            Metric
        </label>

        <select
            id="forecast-metric"
            class="control"
        >
            <option value="orders">
                Orders per day
            </option>

            <option value="revenue">
                Revenue per day
            </option>
        </select>

        <label class="sidebar-label">
            Horizon
        </label>

        <select
            id="forecast-horizon"
            class="control"
        >
            <option value="7">
                Next 7 days
            </option>

            <option value="14">
                Next 14 days
            </option>
        </select>
    `;

    const metric = requireElement(
        "forecast-metric",
    ) as HTMLSelectElement;

    const horizon = requireElement(
        "forecast-horizon",
    ) as HTMLSelectElement;

    metric.value = state.forecastMetric;

    horizon.value = String(
        state.forecastHorizon,
    );

    metric.addEventListener("change", () => {
        state.forecastMetric =
            metric.value as ForecastMetric;

        onChange();
    });

    horizon.addEventListener("change", () => {
        state.forecastHorizon = Number(
            horizon.value,
        );

        onChange();
    });
}
