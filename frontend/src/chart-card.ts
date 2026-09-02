import { mountChart } from "./charts";
import type { ChartSpec } from "./charts";
import { token } from "./theme";

/**
 * The card a chart lives in: title, legend, a chart/table
 * switch, and the plot.
 *
 * The table is not a nicety. A tooltip must enhance the chart,
 * never gate it, so every value the hover layer shows is also
 * readable as text - which is also what makes the chart usable
 * with a screen reader or without a pointer.
 */
export interface ChartCardSpec extends ChartSpec {
    title: string;
    subtitle?: string;
    /** Column header for the label column. */
    labelHeader?: string;
}

function button(
    text: string,
    pressed: boolean,
): HTMLButtonElement {
    const node = document.createElement("button");

    node.type = "button";
    node.className = "view-option";
    node.textContent = text;

    node.setAttribute(
        "aria-pressed",
        String(pressed),
    );

    return node;
}

function legend(spec: ChartCardSpec): HTMLElement | null {
    const visible = spec.series.filter(
        (series) => !series.silent,
    );

    // One series needs no legend: the title already names it.
    if (visible.length < 2) {
        return null;
    }

    const box = document.createElement("div");

    box.className = "chart-legend";

    for (const series of visible) {
        const item = document.createElement("span");

        item.className = "legend-item";

        const key = document.createElement("span");

        key.className =
            series.kind === "band"
                ? "legend-key area"
                : "legend-key";

        // The legend mirrors the mark: a dashed series gets a
        // dashed key, so the dash carries identity alongside
        // hue rather than colour doing the job alone.
        if (series.dashed === true) {
            key.classList.add("dashed");
        }

        // The key carries the series color; the text stays in
        // an ink token so it never becomes illegible.
        key.style.color = token(series.color);

        const label = document.createElement("span");

        label.textContent = series.label;

        item.append(key, label);

        box.append(item);
    }

    return box;
}

function table(spec: ChartCardSpec): HTMLElement {
    const wrap = document.createElement("div");

    wrap.className = "table-wrap";

    const node = document.createElement("table");

    const head = document.createElement("thead");

    const headRow = document.createElement("tr");

    const columns: string[] = [
        spec.labelHeader ?? "Day",
    ];

    for (const series of spec.series) {
        if (series.kind === "band") {
            columns.push(
                `${series.label} low`,
                `${series.label} high`,
            );

            continue;
        }

        columns.push(series.label);
    }

    for (const column of columns) {
        const cell = document.createElement("th");

        cell.textContent = column;

        headRow.append(cell);
    }

    head.append(headRow);

    const body = document.createElement("tbody");

    const formatLabel =
        spec.formatLabel ?? ((value: string) => value);

    spec.labels.forEach((label, index) => {
        const row = document.createElement("tr");

        const first = document.createElement("td");

        first.textContent = formatLabel(label);

        row.append(first);

        for (const series of spec.series) {
            const value = series.values[index];

            if (series.kind === "band") {
                const low = series.lower?.[index];

                const lowCell =
                    document.createElement("td");

                lowCell.textContent =
                    low === null || low === undefined
                        ? "—"
                        : spec.formatValue(low);

                const highCell =
                    document.createElement("td");

                highCell.textContent =
                    value === null ||
                    value === undefined
                        ? "—"
                        : spec.formatValue(value);

                row.append(lowCell, highCell);

                continue;
            }

            const cell = document.createElement("td");

            cell.textContent =
                value === null || value === undefined
                    ? "—"
                    : spec.formatValue(value);

            row.append(cell);
        }

        body.append(row);
    });

    node.append(head, body);

    wrap.append(node);

    return wrap;
}

export function chartCard(
    spec: ChartCardSpec,
): HTMLElement {
    const card = document.createElement("div");

    card.className = "chart";

    const head = document.createElement("div");

    head.className = "chart-head";

    const heading = document.createElement("div");

    const title = document.createElement("div");

    title.className = "chart-title";
    title.textContent = spec.title;

    heading.append(title);

    if (spec.subtitle !== undefined) {
        const subtitle = document.createElement("div");

        subtitle.className = "chart-subtitle";
        subtitle.textContent = spec.subtitle;

        heading.append(subtitle);
    }

    const toggle = document.createElement("div");

    toggle.className = "view-toggle";

    const chartButton = button("Chart", true);
    const tableButton = button("Table", false);

    toggle.append(chartButton, tableButton);

    head.append(heading, toggle);

    card.append(head);

    const key = legend(spec);

    if (key !== null) {
        card.append(key);
    }

    const plot = document.createElement("div");

    plot.className = "plot";

    card.append(plot);

    // Held so the table view can release the chart's resize
    // observer; without that the observer sees the swap as a
    // resize and redraws the chart over the table.
    let release: (() => void) | null = null;

    const showChart = (): void => {
        if (release !== null) {
            release();
            release = null;
        }

        chartButton.setAttribute(
            "aria-pressed",
            "true",
        );

        tableButton.setAttribute(
            "aria-pressed",
            "false",
        );

        plot.replaceChildren();

        release = mountChart(plot, spec);
    };

    const showTable = (): void => {
        if (release !== null) {
            release();
            release = null;
        }

        chartButton.setAttribute(
            "aria-pressed",
            "false",
        );

        tableButton.setAttribute(
            "aria-pressed",
            "true",
        );

        plot.removeAttribute("tabindex");
        plot.removeAttribute("role");
        plot.removeAttribute("aria-label");

        plot.replaceChildren(table(spec));
    };

    chartButton.addEventListener("click", showChart);
    tableButton.addEventListener("click", showTable);

    // Mounted by the caller once the card is in the document,
    // because the chart measures its container.
    queueMicrotask(showChart);

    return card;
}
