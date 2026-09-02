import { fetchSignals } from "../api";
import {
    escapeHtml,
    formatInt,
    formatMoney,
    severityGlyph,
} from "../format";
import { content } from "../state";
import type { SignalMap } from "../types";

/**
 * The anomaly cards, shared by the Overview summary and
 * the dedicated Signals page.
 */
export function renderSignalGrid(
    element: HTMLElement,
    signals: SignalMap,
): void {
    const values = Object.values(signals);

    if (!values.length) {
        element.innerHTML = `
            <div class="notice">
                No anomaly data available.
            </div>
        `;

        return;
    }

    element.innerHTML = values
        .map((signal) => {
            const currency = signal.currency_code;

            const moneyMetric =
                signal.metric === "revenue" ||
                signal.metric === "aov";

            const current = moneyMetric
                ? formatMoney(
                      signal.current_value,
                      currency,
                  )
                : formatInt(signal.current_value);

            const baseline =
                signal.baseline_value === null
                    ? "N/A"
                    : moneyMetric
                      ? formatMoney(
                            signal.baseline_value,
                            currency,
                        )
                      : formatInt(
                            signal.baseline_value,
                        );

            const deviation =
                signal.deviation_pct === null
                    ? "N/A"
                    : `${Number(
                          signal.deviation_pct,
                      ).toFixed(2)}%`;

            return `
                    <div class="signal-card">

                        <div class="signal-name">
                            ${escapeHtml(
                                signal.metric.replaceAll(
                                    "_",
                                    " ",
                                ),
                            )}
                        </div>

                        <div class="signal-value">
                            ${escapeHtml(current)}
                        </div>

                        <div class="signal-meta">
                            7d baseline:
                            ${escapeHtml(baseline)}
                            ·
                            ${escapeHtml(deviation)}
                        </div>

                        <span
                            class="badge ${escapeHtml(
                                signal.severity,
                            )}"
                        >
                            <span
                                class="badge-glyph"
                                aria-hidden="true"
                            >${severityGlyph(
                                signal.severity,
                            )}</span>

                            ${escapeHtml(
                                signal.severity,
                            )}
                        </span>

                        <div class="signal-reason">
                            ${escapeHtml(
                                signal.reason,
                            )}
                        </div>

                    </div>
                `;
        })
        .join("");
}

export async function renderSignals(): Promise<void> {
    const data = await fetchSignals();

    content.innerHTML = `

        ${
            data.error
                ? `
            <div class="notice">
                ${escapeHtml(data.error)}
            </div>
            `
                : ""
        }

        <div
            id="signal-page"
            class="signal-grid"
        ></div>

    `;

    const grid = content.querySelector<HTMLElement>(
        "#signal-page",
    );

    if (grid !== null) {
        renderSignalGrid(grid, data.signals);
    }
}
