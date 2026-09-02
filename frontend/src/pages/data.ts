import { fetchDataHealth } from "../api";
import {
    escapeHtml,
    formatInt,
    formatTimestamp,
    metricCard,
} from "../format";
import { content } from "../state";

export async function renderData(): Promise<void> {
    const data = await fetchDataHealth();

    const rows = Object.entries(data.counts)
        .map(
            ([table, count]) => `
                <tr>
                    <td>
                        ${escapeHtml(table)}
                    </td>

                    <td>
                        ${formatInt(count)}
                    </td>
                </tr>
            `,
        )
        .join("");

    content.innerHTML = `

        <div class="grid">

            ${metricCard(
                "Orders",
                formatInt(data.counts["orders"]),
            )}

            ${metricCard(
                "Product variants",
                formatInt(
                    data.counts[
                        "product_variants"
                    ],
                ),
            )}

            ${metricCard(
                "Inventory items",
                formatInt(
                    data.latest_inventory_items,
                ),
            )}

            ${metricCard(
                "Order range",
                (data.order_start || "N/A") +
                    " → " +
                    (data.order_end || "N/A"),
            )}

        </div>


        <div class="section-title">
            Sync status
        </div>


        <div class="card">

            <p>
                <strong>
                    Orders:
                </strong>

                ${escapeHtml(
                    formatTimestamp(
                        data.orders_synced_at,
                    ),
                )}
            </p>

            <p>
                <strong>
                    Inventory:
                </strong>

                ${escapeHtml(
                    formatTimestamp(
                        data.inventory_synced_at,
                    ),
                )}
            </p>

            <p>
                <strong>
                    ShopifyQL:
                </strong>

                ${escapeHtml(
                    formatTimestamp(
                        data.analytics_synced_at,
                    ),
                )}
            </p>

        </div>


        <div class="section-title">
            DuckDB tables
        </div>


        <div class="table-wrap">

            <table>

                <thead>
                    <tr>
                        <th>Table</th>
                        <th>Rows</th>
                    </tr>
                </thead>

                <tbody>
                    ${rows}
                </tbody>

            </table>

        </div>

    `;
}
