/**
 * Value formatting and HTML escaping.
 *
 * Every page builds its markup with template strings,
 * so anything derived from the database goes through
 * escapeHtml before it reaches innerHTML.
 */

export function escapeHtml(
    value: unknown,
): string {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

export function formatMoney(
    value: number | null | undefined,
    currency?: string,
): string {
    if (value === null || value === undefined) {
        return "N/A";
    }

    const formatted = Number(
        value,
    ).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });

    return (
        formatted + (currency ? ` ${currency}` : "")
    );
}

/**
 * Rounds, because the name promises an integer.
 *
 * Several of these values are means rather than counts - a
 * 7-day baseline, a predicted order count - and passing them
 * through unrounded printed "122.143" beside a whole number
 * like 57, which reads as false precision.
 */
export function formatInt(
    value: number | null | undefined,
): string {
    if (value === null || value === undefined) {
        return "N/A";
    }

    return Math.round(
        Number(value),
    ).toLocaleString();
}

export function formatPercent(
    value: number | null | undefined,
): string {
    if (value === null || value === undefined) {
        return "N/A";
    }

    return (Number(value) * 100).toFixed(2) + "%";
}

/**
 * Three states, not two.
 *
 * `undefined` means the metric has no comparison at all (a
 * count of locations, a model name) and gets no delta line;
 * `null` means a comparison exists but the previous period is
 * missing, which is worth saying. Collapsing the two put
 * "No previous period" under every stat tile on the page.
 */
export function deltaHtml(
    value: number | null | undefined,
): string {
    if (value === undefined) {
        return "";
    }

    if (value === null) {
        return `<div class="metric-delta">
                No previous period
            </div>`;
    }

    const className = value >= 0 ? "up" : "down";

    const sign = value > 0 ? "+" : "";

    return `<div class="metric-delta ${className}">
            ${sign}${value.toFixed(1)}%
            vs previous period
        </div>`;
}

export function metricCard(
    label: string,
    value: string,
    delta?: number | null,
    extraClass = "",
): string {
    return `
        <div class="card ${extraClass}">

            <div class="metric-label">
                ${escapeHtml(label)}
            </div>

            <div class="metric-value">
                ${escapeHtml(value)}
            </div>

            ${deltaHtml(delta)}

        </div>
    `;
}

/**
 * "2026-08-04" -> "Aug 4".
 *
 * Parsed as UTC on purpose: these are calendar days from
 * DuckDB, not instants, and letting the local timezone shift
 * them slides every axis label by a day west of Greenwich.
 */
export function formatDay(iso: string): string {
    const parsed = new Date(`${iso}T00:00:00Z`);

    if (Number.isNaN(parsed.getTime())) {
        return iso;
    }

    return parsed.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
    });
}

/**
 * Compact form for stat tiles: 1,284 / 12.9K / 4.2M.
 */
export function formatCompact(
    value: number | null | undefined,
): string {
    if (value === null || value === undefined) {
        return "N/A";
    }

    const absolute = Math.abs(value);

    if (absolute >= 1_000_000) {
        return (
            (value / 1_000_000).toFixed(1) + "M"
        );
    }

    if (absolute >= 10_000) {
        return (value / 1000).toFixed(1) + "K";
    }

    return Math.round(value).toLocaleString();
}

/**
 * Severity glyph. Status colour never travels alone: the badge
 * pairs this with the severity name, so the state survives
 * colour blindness, greyscale print and forced-colors.
 */
export function severityGlyph(
    severity: string,
): string {
    if (severity === "NORMAL") {
        return "\u25CF";
    }

    if (severity === "CRITICAL") {
        return "\u25B2";
    }

    if (severity === "WARNING") {
        return "\u25B3";
    }

    return "\u25CB";
}

/**
 * A sync timestamp as something a person reads.
 *
 * DuckDB hands these back as full ISO strings with microsecond
 * precision - "2026-09-02T09:11:44.718267+08:00" - which is
 * accurate and unreadable. The offset is preserved by letting
 * Date parse it and rendering in the reader's own zone.
 */
export function formatTimestamp(
    iso: string | null | undefined,
): string {
    if (iso === null || iso === undefined) {
        return "N/A";
    }

    const parsed = new Date(iso);

    if (Number.isNaN(parsed.getTime())) {
        return iso;
    }

    return parsed.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    });
}
