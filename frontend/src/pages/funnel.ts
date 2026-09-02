import { fetchFunnel } from "../api";
import {
    escapeHtml,
    formatInt,
    formatPercent,
    metricCard,
} from "../format";
import { content } from "../state";

export async function renderFunnel(): Promise<void> {
    const response = await fetchFunnel();

    const data = response.data;

    if (!response.available || data === null) {
        content.innerHTML = `
            <div class="notice">
                ShopifyQL funnel snapshot
                is not available.
            </div>
        `;

        return;
    }

    // Funnel stages are ordered, so they take the ordinal
    // ramp - one hue, light to dark - rather than four
    // categorical hues, which would imply four unrelated
    // things instead of one narrowing flow.
    const stages: Array<
        [string, number, string]
    > = [
        ["Sessions", data.sessions, "--step-1"],

        [
            "Cart additions",
            data.sessions_with_cart_additions,
            "--step-2",
        ],

        [
            "Reached checkout",
            data.sessions_that_reached_checkout,
            "--step-3",
        ],

        [
            "Completed checkout",
            data.sessions_that_completed_checkout,
            "--step-4",
        ],
    ];

    const maximum = Math.max(
        Number(data.sessions || 0),
        1,
    );

    const funnelRows = stages
        .map(([name, value, step]) => {
            const percentage =
                (Number(value || 0) / maximum) *
                100;

            return `
                    <div class="funnel-row">

                        <div class="funnel-header">

                            <span>
                                ${escapeHtml(name)}
                            </span>

                            <span>
                                ${formatInt(value)}
                                <span class="funnel-share">
                                    ${percentage.toFixed(1)}%
                                </span>
                            </span>

                        </div>

                        <div class="funnel-track">

                            <div
                                class="funnel-fill"
                                style="
                                    width: ${percentage}%;
                                    background: var(${step});
                                "
                            ></div>

                        </div>

                    </div>
                `;
        })
        .join("");

    content.innerHTML = `

        <div class="grid">

            ${metricCard(
                "Sessions",
                formatInt(data.sessions),
            )}

            ${metricCard(
                "Visitors",
                formatInt(
                    data.online_store_visitors,
                ),
            )}

            ${metricCard(
                "Conversion",
                formatPercent(
                    data.conversion_rate,
                ),
            )}

            ${metricCard(
                "Completed checkout",
                formatInt(
                    data.sessions_that_completed_checkout,
                ),
            )}

        </div>


        <div class="section-title">
            Session → checkout funnel
        </div>


        <div class="card">
            ${funnelRows}
        </div>

    `;
}
