import { fetchOverview } from "../api";
import { chartCard } from "../chart-card";
import {
    escapeHtml,
    formatCompact,
    formatDay,
    formatInt,
    formatMoney,
    formatPercent,
    metricCard,
} from "../format";
import { content, state } from "../state";
import { renderSignalGrid } from "./signals";

export async function renderOverview(): Promise<void> {
    const data = await fetchOverview(state.days);

    const current = data.current;

    const currency = current.currency_code;

    // Revenue is the one hero figure on this view; the rest
    // are ordinary stat tiles. More than one hero and none of
    // them leads.
    content.innerHTML = `

        <div class="notice">

            Requested:
            <strong>
                ${data.requested_days} days
            </strong>

            ·

            Available:
            <strong>
                ${data.available_days} days
            </strong>

            ·

            Range:
            ${escapeHtml(current.start || "N/A")}
            →
            ${escapeHtml(current.end || "N/A")}

        </div>


        <div class="grid">

            ${metricCard(
                `Revenue · ${currency}`,
                formatCompact(current.revenue),
                data.changes_pct.revenue,
                "hero-figure",
            )}

            ${metricCard(
                "Orders",
                formatInt(current.orders),
                data.changes_pct.orders,
            )}

            ${metricCard(
                "AOV",
                formatMoney(
                    current.aov,
                    currency,
                ),
                data.changes_pct.aov,
            )}

            ${metricCard(
                "Units sold",
                formatInt(current.units_sold),
                data.changes_pct.units_sold,
            )}

        </div>


        <div class="section-title">
            Store health
        </div>

        <div class="grid">

            ${metricCard(
                "Available stock",
                formatCompact(
                    data.inventory.total_available,
                ),
            )}

            ${metricCard(
                "Out-of-stock levels",
                formatCompact(
                    data.inventory
                        .out_of_stock_levels,
                ),
            )}

            ${metricCard(
                "Inventory items",
                formatCompact(
                    data.inventory.inventory_items,
                ),
            )}

            ${metricCard(
                "Conversion rate",
                data.funnel
                    ? formatPercent(
                          data.funnel
                              .conversion_rate,
                      )
                    : "N/A",
            )}

        </div>


        <div class="section-title">
            Sales momentum
        </div>

        <div
            id="momentum"
            class="chart-grid"
        ></div>


        <div class="section-title">
            Signals
        </div>

        <div
            id="signals-grid"
            class="signal-grid"
        ></div>
    `;

    const momentum =
        content.querySelector<HTMLElement>(
            "#momentum",
        );

    const labels = data.trend.map(
        (row) => row.day,
    );

    if (momentum !== null) {
        momentum.append(
            chartCard({
                title: "Revenue",
                subtitle:
                    `Daily revenue in ${currency} ` +
                    "against its trailing 7-day mean",
                labels,
                formatLabel: formatDay,
                formatValue: (value) =>
                    formatMoney(value, currency),
                series: [
                    {
                        label: "Revenue",
                        kind: "line",
                        color: "--series-1",
                        values: data.trend.map(
                            (row) => row.revenue,
                        ),
                    },
                    {
                        label: "7-day mean",
                        kind: "line",
                        color: "--series-2",
                        dashed: true,
                        values: data.trend.map(
                            (row) => row.baseline_7d,
                        ),
                    },
                ],
            }),
        );

        momentum.append(
            chartCard({
                title: "Orders",
                subtitle: "Orders placed per day",
                labels,
                formatLabel: formatDay,
                formatValue: formatInt,
                series: [
                    {
                        label: "Orders",
                        kind: "bar",
                        color: "--series-1",
                        values: data.trend.map(
                            (row) => row.orders,
                        ),
                    },
                ],
            }),
        );
    }

    const signalsGrid =
        content.querySelector<HTMLElement>(
            "#signals-grid",
        );

    if (signalsGrid !== null) {
        renderSignalGrid(
            signalsGrid,
            data.signals,
        );
    }
}
