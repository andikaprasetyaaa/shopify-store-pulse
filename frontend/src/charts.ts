import { token } from "./theme";

/**
 * Interactive SVG charts, drawn by hand.
 *
 * Three things drive the shape of this module:
 *
 * 1. The plot is drawn at real pixel size, measured from the
 *    container, instead of a fixed viewBox stretched with
 *    preserveAspectRatio="none". Stretching distorts stroke
 *    widths and text, and - more importantly here - it makes
 *    pointer coordinates disagree with drawn coordinates, so
 *    a crosshair cannot land on the right day.
 *
 * 2. Colors are read from CSS custom properties at draw time,
 *    so a theme change is a redraw, not a second palette.
 *
 * 3. Everything is built with the DOM API rather than innerHTML
 *    strings. Day labels and series names come from the API,
 *    and textContent means they can never be markup.
 */

export type SeriesKind = "line" | "bar" | "band";

export interface ChartSeries {
    label: string;
    kind: SeriesKind;
    /** A design-token name, e.g. "--series-1". */
    color: string;
    values: Array<number | null>;
    /** Lower edge, band series only. */
    lower?: Array<number | null>;
    dashed?: boolean;
    /** Hidden from the legend (a band shown with its line). */
    silent?: boolean;
}

export interface ChartSpec {
    labels: string[];
    series: ChartSeries[];
    formatValue: (value: number) => string;
    /** Axis/tooltip form of a label; defaults to the label. */
    formatLabel?: (label: string) => string;
    height?: number;
}

const SVG_NS = "http://www.w3.org/2000/svg";

const PAD_TOP = 14;
const PAD_RIGHT = 12;
const PAD_BOTTOM = 26;
const PAD_LEFT = 54;

const DEFAULT_HEIGHT = 240;
const MAX_BAR_WIDTH = 24;
const SURFACE_GAP = 2;

interface Mounted {
    plot: HTMLElement;
    spec: ChartSpec;
    observer: ResizeObserver;
}

const mounted: Mounted[] = [];

/**
 * Charts outlive the innerHTML that created them only through
 * their ResizeObserver, so a page swap has to let them go.
 */
export function disposeCharts(): void {
    for (const chart of mounted) {
        chart.observer.disconnect();
    }

    mounted.length = 0;
}

function el<K extends keyof SVGElementTagNameMap>(
    tag: K,
    attrs: Record<string, string | number> = {},
): SVGElementTagNameMap[K] {
    const node = document.createElementNS(SVG_NS, tag);

    for (const [key, value] of Object.entries(attrs)) {
        node.setAttribute(key, String(value));
    }

    return node;
}

function div(
    className: string,
    text?: string,
): HTMLDivElement {
    const node = document.createElement("div");

    node.className = className;

    if (text !== undefined) {
        node.textContent = text;
    }

    return node;
}

/**
 * Axis steps a reader can do arithmetic with: 1, 2 or 5 times
 * a power of ten, never the raw range divided by four.
 */
function niceStep(range: number, count: number): number {
    if (range <= 0) {
        return 1;
    }

    const raw = range / count;

    const magnitude = 10 ** Math.floor(
        Math.log10(raw),
    );

    const normalized = raw / magnitude;

    const step =
        normalized <= 1
            ? 1
            : normalized <= 2
              ? 2
              : normalized <= 5
                ? 5
                : 10;

    return step * magnitude;
}

function maxOf(spec: ChartSpec): number {
    const values: number[] = [];

    for (const series of spec.series) {
        for (const value of series.values) {
            if (value !== null) {
                values.push(value);
            }
        }

        for (const value of series.lower ?? []) {
            if (value !== null) {
                values.push(value);
            }
        }
    }

    return values.length ? Math.max(...values) : 1;
}

/** A rect with only its top corners rounded. */
function barPath(
    x: number,
    y: number,
    width: number,
    height: number,
    radius: number,
): string {
    const r = Math.min(radius, width / 2, height);

    return (
        `M${x},${y + height}` +
        `L${x},${y + r}` +
        `Q${x},${y} ${x + r},${y}` +
        `L${x + width - r},${y}` +
        `Q${x + width},${y} ${x + width},${y + r}` +
        `L${x + width},${y + height}` +
        "Z"
    );
}

interface Geometry {
    width: number;
    height: number;
    innerWidth: number;
    innerHeight: number;
    maxValue: number;
    step: number;
    x: (index: number) => number;
    y: (value: number) => number;
    bandWidth: number;
    isBar: boolean;
}

function geometry(
    spec: ChartSpec,
    width: number,
): Geometry {
    const height = spec.height ?? DEFAULT_HEIGHT;

    const innerWidth = Math.max(
        10,
        width - PAD_LEFT - PAD_RIGHT,
    );

    const innerHeight = height - PAD_TOP - PAD_BOTTOM;

    const rawMax = maxOf(spec);

    const step = niceStep(rawMax, 4);

    const maxValue = Math.max(
        Math.ceil(rawMax / step) * step,
        step,
    );

    const count = spec.labels.length;

    const isBar = spec.series.some(
        (series) => series.kind === "bar",
    );

    const bandWidth = innerWidth / Math.max(count, 1);

    const x = isBar
        ? (index: number) =>
              PAD_LEFT +
              bandWidth * index +
              bandWidth / 2
        : (index: number) =>
              count <= 1
                  ? PAD_LEFT + innerWidth / 2
                  : PAD_LEFT +
                    (index / (count - 1)) * innerWidth;

    const y = (value: number) =>
        PAD_TOP +
        innerHeight -
        (value / maxValue) * innerHeight;

    return {
        width,
        height,
        innerWidth,
        innerHeight,
        maxValue,
        step,
        x,
        y,
        bandWidth,
        isBar,
    };
}

/**
 * Picks as many x labels as fit without collision, always
 * including the first and last.
 */
function tickIndices(
    count: number,
    innerWidth: number,
): number[] {
    if (count === 0) {
        return [];
    }

    const maxTicks = Math.max(
        2,
        Math.min(7, Math.floor(innerWidth / 90)),
    );

    if (count <= maxTicks) {
        return Array.from(
            { length: count },
            (_, index) => index,
        );
    }

    const stride = Math.ceil(count / maxTicks);

    const indices: number[] = [];

    for (
        let index = 0;
        index < count;
        index += stride
    ) {
        indices.push(index);
    }

    if (indices[indices.length - 1] !== count - 1) {
        indices.push(count - 1);
    }

    return indices;
}

function drawAxes(
    svg: SVGSVGElement,
    spec: ChartSpec,
    geo: Geometry,
): void {
    const grid = token("--grid");
    const axis = token("--axis");
    const muted = token("--text-muted");

    for (
        let value = 0;
        value <= geo.maxValue + geo.step / 2;
        value += geo.step
    ) {
        const y = geo.y(value);

        svg.append(
            el("line", {
                x1: PAD_LEFT,
                y1: y,
                x2: PAD_LEFT + geo.innerWidth,
                y2: y,
                stroke: value === 0 ? axis : grid,
                "stroke-width": 1,
            }),
        );

        const label = el("text", {
            x: PAD_LEFT - 9,
            y: y + 3.5,
            "text-anchor": "end",
            fill: muted,
            "font-size": 10.5,
            "font-variant-numeric": "tabular-nums",
        });

        label.textContent = compact(value);

        svg.append(label);
    }

    const formatLabel =
        spec.formatLabel ?? ((value: string) => value);

    for (const index of tickIndices(
        spec.labels.length,
        geo.innerWidth,
    )) {
        const raw = spec.labels[index];

        if (raw === undefined) {
            continue;
        }

        const text = el("text", {
            x: geo.x(index),
            y: geo.height - 8,
            "text-anchor": "middle",
            fill: muted,
            "font-size": 10.5,
        });

        text.textContent = formatLabel(raw);

        svg.append(text);
    }
}

/** Axis ticks stay short: 1.2K rather than 1,200. */
function compact(value: number): string {
    const absolute = Math.abs(value);

    if (absolute >= 1_000_000) {
        return (
            (value / 1_000_000)
                .toFixed(absolute >= 10_000_000 ? 0 : 1)
                .replace(/\.0$/, "") + "M"
        );
    }

    if (absolute >= 1000) {
        return (
            (value / 1000)
                .toFixed(absolute >= 10_000 ? 0 : 1)
                .replace(/\.0$/, "") + "K"
        );
    }

    return String(Math.round(value * 100) / 100);
}

/** Consecutive runs of non-null points, so gaps stay gaps. */
function segments(
    values: Array<number | null>,
): Array<Array<{ index: number; value: number }>> {
    const runs: Array<
        Array<{ index: number; value: number }>
    > = [];

    let run: Array<{ index: number; value: number }> =
        [];

    values.forEach((value, index) => {
        if (value === null) {
            if (run.length) {
                runs.push(run);
            }

            run = [];

            return;
        }

        run.push({ index, value });
    });

    if (run.length) {
        runs.push(run);
    }

    return runs;
}

function drawSeries(
    svg: SVGSVGElement,
    spec: ChartSpec,
    geo: Geometry,
): void {
    const surface = token("--surface");

    for (const series of spec.series) {
        const color = token(series.color);

        if (series.kind === "band") {
            drawBand(svg, series, geo, color);

            continue;
        }

        if (series.kind === "bar") {
            drawBars(svg, series, geo, color);

            continue;
        }

        for (const run of segments(series.values)) {
            if (run.length === 1) {
                const only = run[0];

                if (only === undefined) {
                    continue;
                }

                svg.append(
                    el("circle", {
                        cx: geo.x(only.index),
                        cy: geo.y(only.value),
                        r: 4,
                        fill: color,
                        stroke: surface,
                        "stroke-width": SURFACE_GAP,
                    }),
                );

                continue;
            }

            const points = run
                .map(
                    (point) =>
                        `${geo.x(point.index)},` +
                        `${geo.y(point.value)}`,
                )
                .join(" ");

            svg.append(
                el("polyline", {
                    points,
                    fill: "none",
                    stroke: color,
                    "stroke-width": 2,
                    "stroke-linejoin": "round",
                    "stroke-linecap": "round",
                    ...(series.dashed
                        ? { "stroke-dasharray": "6 5" }
                        : {}),
                }),
            );
        }
    }
}

function drawBand(
    svg: SVGSVGElement,
    series: ChartSeries,
    geo: Geometry,
    color: string,
): void {
    const upper: string[] = [];
    const lower: string[] = [];

    series.values.forEach((value, index) => {
        const floor = series.lower?.[index];

        if (
            value === null ||
            floor === null ||
            floor === undefined
        ) {
            return;
        }

        upper.push(
            `${geo.x(index)},${geo.y(value)}`,
        );

        lower.unshift(
            `${geo.x(index)},${geo.y(floor)}`,
        );
    });

    if (!upper.length) {
        return;
    }

    svg.append(
        el("polygon", {
            points: upper.concat(lower).join(" "),
            fill: color,
            "fill-opacity": 0.12,
            stroke: "none",
        }),
    );
}

function drawBars(
    svg: SVGSVGElement,
    series: ChartSeries,
    geo: Geometry,
    color: string,
): void {
    // Capped, never filling the slot: the leftover band is
    // the surface gap between neighbours.
    const width = Math.max(
        2,
        Math.min(
            MAX_BAR_WIDTH,
            geo.bandWidth - SURFACE_GAP,
        ),
    );

    series.values.forEach((value, index) => {
        if (value === null) {
            return;
        }

        const y = geo.y(value);

        const height = geo.y(0) - y;

        if (height <= 0) {
            return;
        }

        svg.append(
            el("path", {
                d: barPath(
                    geo.x(index) - width / 2,
                    y,
                    width,
                    height,
                    4,
                ),
                fill: color,
                "data-bar": index,
            }),
        );
    });
}

/**
 * The hover layer.
 *
 * Line charts get a crosshair that snaps to the nearest day,
 * because nobody can aim at a 2px line. Bar charts highlight
 * the hovered bar instead, and the hit target is the whole
 * band, not the painted rectangle.
 *
 * Keyboard gets the same readout: the plot is focusable and
 * the arrow keys walk the same index.
 */
function addInteraction(
    plot: HTMLElement,
    svg: SVGSVGElement,
    spec: ChartSpec,
    geo: Geometry,
): void {
    if (!spec.labels.length) {
        return;
    }

    const overlayGroup = el("g");

    svg.append(overlayGroup);

    const tooltip = div("tooltip");

    tooltip.setAttribute("role", "status");

    plot.append(tooltip);

    const formatLabel =
        spec.formatLabel ?? ((value: string) => value);

    let active = -1;

    const clear = (): void => {
        active = -1;

        overlayGroup.replaceChildren();

        tooltip.dataset["visible"] = "false";
    };

    const show = (index: number): void => {
        if (index === active) {
            return;
        }

        active = index;

        overlayGroup.replaceChildren();

        const surface = token("--surface");

        if (geo.isBar) {
            overlayGroup.append(
                el("rect", {
                    x:
                        geo.x(index) -
                        geo.bandWidth / 2,
                    y: PAD_TOP,
                    width: geo.bandWidth,
                    height: geo.innerHeight,
                    fill: token("--text"),
                    "fill-opacity": 0.06,
                    rx: 4,
                }),
            );
        } else {
            overlayGroup.append(
                el("line", {
                    x1: geo.x(index),
                    y1: PAD_TOP,
                    x2: geo.x(index),
                    y2: PAD_TOP + geo.innerHeight,
                    stroke: token("--axis"),
                    "stroke-width": 1,
                }),
            );
        }

        const rows: Array<{
            label: string;
            value: number;
            color: string;
        }> = [];

        for (const series of spec.series) {
            const value = series.values[index];

            if (value === null || value === undefined) {
                continue;
            }

            const color = token(series.color);

            rows.push({
                label: series.label,
                value,
                color,
            });

            if (series.kind === "line") {
                // A dot with a surface ring, so it stays
                // legible where series overlap.
                overlayGroup.append(
                    el("circle", {
                        cx: geo.x(index),
                        cy: geo.y(value),
                        r: 4,
                        fill: color,
                        stroke: surface,
                        "stroke-width": SURFACE_GAP,
                    }),
                );
            }
        }

        if (!rows.length) {
            tooltip.dataset["visible"] = "false";

            return;
        }

        tooltip.replaceChildren();

        const rawLabel = spec.labels[index] ?? "";

        tooltip.append(
            div("tooltip-title", formatLabel(rawLabel)),
        );

        for (const row of rows) {
            const line = div("tooltip-row");

            const key = div("tooltip-key");

            key.style.background = row.color;

            const label = div(
                "tooltip-label",
                row.label,
            );

            const value = div(
                "tooltip-value",
                spec.formatValue(row.value),
            );

            line.append(key, label, value);

            tooltip.append(line);
        }

        tooltip.dataset["visible"] = "true";

        // Flip the tooltip to the other side of the
        // crosshair near the right edge so it never leaves
        // the card.
        const anchor = geo.x(index);

        const width = tooltip.offsetWidth;

        const left =
            anchor + width + 18 > geo.width
                ? anchor - width - 14
                : anchor + 14;

        tooltip.style.left = `${Math.max(0, left)}px`;

        tooltip.style.top = `${PAD_TOP + 4}px`;
    };

    const indexFromPointer = (
        clientX: number,
    ): number => {
        const box = svg.getBoundingClientRect();

        const offset = clientX - box.left;

        if (geo.isBar) {
            const raw = Math.floor(
                (offset - PAD_LEFT) / geo.bandWidth,
            );

            return Math.min(
                spec.labels.length - 1,
                Math.max(0, raw),
            );
        }

        if (spec.labels.length === 1) {
            return 0;
        }

        const stride =
            geo.innerWidth / (spec.labels.length - 1);

        const raw = Math.round(
            (offset - PAD_LEFT) / stride,
        );

        return Math.min(
            spec.labels.length - 1,
            Math.max(0, raw),
        );
    };

    svg.addEventListener("pointermove", (event) => {
        show(indexFromPointer(event.clientX));
    });

    svg.addEventListener("pointerleave", clear);

    plot.tabIndex = 0;

    plot.setAttribute("role", "img");

    plot.setAttribute(
        "aria-label",
        `${spec.series
            .map((series) => series.label)
            .join(", ")}. ` +
            "Use the arrow keys to read each point, " +
            "or switch to the table view.",
    );

    plot.addEventListener("keydown", (event) => {
        const last = spec.labels.length - 1;

        if (event.key === "ArrowRight") {
            show(Math.min(last, active + 1));
        } else if (event.key === "ArrowLeft") {
            show(Math.max(0, (active < 0 ? 1 : active) - 1));
        } else if (event.key === "Home") {
            show(0);
        } else if (event.key === "End") {
            show(last);
        } else if (event.key === "Escape") {
            clear();

            return;
        } else {
            return;
        }

        event.preventDefault();
    });

    plot.addEventListener("blur", clear);
}

function draw(plot: HTMLElement, spec: ChartSpec): void {
    const width = plot.clientWidth;

    if (width === 0) {
        return;
    }

    const geo = geometry(spec, width);

    const svg = el("svg", {
        width,
        height: geo.height,
        viewBox: `0 0 ${width} ${geo.height}`,
    });

    drawAxes(svg, spec, geo);

    drawSeries(svg, spec, geo);

    plot.replaceChildren(svg);

    addInteraction(plot, svg, spec, geo);
}

/**
 * Draws the chart into `plot` and keeps it correct: it
 * redraws on resize, and on any theme change, since the
 * colors come from CSS custom properties.
 *
 * Returns a disposer, and callers must use it. The resize
 * observer is what makes the chart responsive, but it also
 * means that replacing the plot's contents - switching to the
 * table view, say - changes the element's height, fires the
 * observer, and redraws the chart straight back over the
 * replacement. Releasing the observer first is the fix.
 */
export function mountChart(
    plot: HTMLElement,
    spec: ChartSpec,
): () => void {
    if (
        !spec.labels.length ||
        !spec.series.some((series) =>
            series.values.some(
                (value) => value !== null,
            ),
        )
    ) {
        plot.replaceChildren(
            div("chart-empty", "No data for this range."),
        );

        return () => {};
    }

    const observer = new ResizeObserver(() => {
        draw(plot, spec);
    });

    observer.observe(plot);

    const entry: Mounted = { plot, spec, observer };

    mounted.push(entry);

    draw(plot, spec);

    return () => {
        observer.disconnect();

        const index = mounted.indexOf(entry);

        if (index !== -1) {
            mounted.splice(index, 1);
        }
    };
}

/** Redraws every live chart, e.g. after a theme change. */
export function redrawCharts(): void {
    for (const chart of mounted) {
        draw(chart.plot, chart.spec);
    }
}
