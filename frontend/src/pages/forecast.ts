import { fetchForecast } from "../api";
import { chartCard } from "../chart-card";
import {
    escapeHtml,
    formatDay,
    formatInt,
    formatMoney,
    metricCard,
} from "../format";
import { content, state } from "../state";
import type { ForecastAccuracy } from "../types";

/**
 * The forecast page.
 *
 * /api/forecast already returned everything needed for
 * this, but nothing in the dashboard was reading it.
 *
 * The accuracy block is not decoration. The model is
 * only deployed because it beats a seasonal naive
 * benchmark in a rolling-origin backtest, and showing
 * both numbers side by side is what lets a reader judge
 * the forecast instead of trusting it.
 */
export async function renderForecast(): Promise<void> {
    const data = await fetchForecast(
        state.forecastMetric,
        state.forecastHorizon,
    );

    const isMoney = data.metric === "revenue";

    // Predictions come back as floats. Revenue keeps its
    // cents; a count of orders goes through formatInt, which
    // rounds, the same way scripts/check_forecast.py prints
    // it.
    const format = (value: number): string =>
        isMoney
            ? formatMoney(value)
            : formatInt(value);

    if (data.error) {
        content.innerHTML = `
            <div class="error">
                ${escapeHtml(data.error)}
            </div>
        `;

        return;
    }

    const rows = data.forecast
        .map(
            (point) => `
                <tr>
                    <td>
                        ${escapeHtml(point.day)}
                    </td>

                    <td>
                        ${format(point.predicted)}
                    </td>

                    <td>
                        ${format(point.lower)}
                        –
                        ${format(point.upper)}
                    </td>
                </tr>
            `,
        )
        .join("");

    const first = data.forecast[0];

    content.innerHTML = `

        <div class="grid">

            ${metricCard(
                "Model",
                data.model ?? "N/A",
            )}

            ${metricCard(
                "Horizon",
                `${data.forecast.length} days`,
            )}

            ${metricCard(
                "Next day",
                first === undefined
                    ? "N/A"
                    : format(first.predicted),
            )}

            ${metricCard(
                "History used",
                `${data.history.length} days`,
            )}

        </div>


        ${accuracyHtml(data.accuracy)}


        <div class="section-title">
            History and forecast
        </div>

        <div id="forecast-chart"></div>


        <div class="section-title">
            Predicted ${escapeHtml(data.metric)}
        </div>

        <div class="table-wrap">

            <table>

                <thead>
                    <tr>
                        <th>Day</th>
                        <th>Predicted</th>
                        <th>80% band</th>
                    </tr>
                </thead>

                <tbody>
                    ${
                        rows ||
                        `
                        <tr>
                            <td colspan="3">
                                No forecast available.
                            </td>
                        </tr>
                        `
                    }
                </tbody>

            </table>

        </div>
    `;

    const chart = content.querySelector<HTMLElement>(
        "#forecast-chart",
    );

    if (chart === null) {
        return;
    }

    // History and forecast share one axis, so they are one
    // series list over a single label track: actual days
    // first, then the predicted ones, with each series null
    // where the other is drawn.
    const labels = data.history
        .map((point) => point.day)
        .concat(
            data.forecast.map((point) => point.day),
        );

    const pad = (
        count: number,
    ): Array<number | null> =>
        Array.from({ length: count }, () => null);

    const actual: Array<number | null> = data.history
        .map((point): number | null => point.value)
        .concat(pad(data.forecast.length));

    // The predicted line starts on the last actual point so
    // the two meet instead of leaving a visual gap.
    const lastActual =
        data.history[data.history.length - 1];

    const predicted: Array<number | null> = pad(
        Math.max(0, data.history.length - 1),
    )
        .concat(
            data.history.length && lastActual
                ? [lastActual.value]
                : [],
        )
        .concat(
            data.forecast.map(
                (point) => point.predicted,
            ),
        );

    const upper: Array<number | null> = pad(
        data.history.length,
    ).concat(
        data.forecast.map((point) => point.upper),
    );

    const lower: Array<number | null> = pad(
        data.history.length,
    ).concat(
        data.forecast.map((point) => point.lower),
    );

    chart.append(
        chartCard({
            title: `Forecast · ${data.metric}`,
            subtitle:
                `${data.history.length} days of history, ` +
                `${data.forecast.length} days ahead`,
            labels,
            formatLabel: formatDay,
            formatValue: format,
            series: [
                {
                    label: "80% band",
                    kind: "band",
                    color: "--series-2",
                    values: upper,
                    lower,
                },
                {
                    label: "Actual",
                    kind: "line",
                    color: "--series-1",
                    values: actual,
                },
                {
                    label: "Forecast",
                    kind: "line",
                    color: "--series-2",
                    dashed: true,
                    values: predicted,
                },
            ],
        }),
    );
}

/**
 * The deployed model's backtest score against the
 * benchmark it had to beat.
 *
 * A negative improvement is reported plainly rather
 * than hidden: at the longest horizons the benchmark
 * does catch up, and a reader is better served knowing
 * that than seeing an unqualified win.
 */
function accuracyHtml(
    accuracy: ForecastAccuracy | null,
): string {
    if (accuracy === null) {
        return `
            <div class="notice">
                Not enough history to backtest this
                horizon, so no accuracy is reported.
            </div>
        `;
    }

    const improvement =
        ((accuracy.benchmark_mape -
            accuracy.model_mape) /
            accuracy.benchmark_mape) *
        100;

    const verdict =
        improvement > 0
            ? `beats the benchmark by
               ${improvement.toFixed(1)}%`
            : `does not beat the benchmark
               (${improvement.toFixed(1)}%)`;

    return `
        <div class="notice">

            Rolling-origin backtest over
            <strong>
                ${accuracy.folds} folds
            </strong>

            ·

            Model MAPE
            <strong>
                ${accuracy.model_mape.toFixed(1)}%
            </strong>

            vs
            ${escapeHtml(accuracy.benchmark)}
            <strong>
                ${accuracy.benchmark_mape.toFixed(
                    1,
                )}%
            </strong>

            ·

            ${verdict}

        </div>
    `;
}
