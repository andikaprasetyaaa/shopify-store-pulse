import { fetchInventory } from "../api";
import {
    escapeHtml,
    formatInt,
    metricCard,
} from "../format";
import { content, state } from "../state";

export async function renderInventory(): Promise<void> {
    const data = await fetchInventory(
        state.threshold,
        state.search,
    );

    const summary = data.summary;

    const rows = data.items
        .map(
            (item) => `
                <tr>

                    <td>
                        ${escapeHtml(
                            item.product_title,
                        )}
                    </td>

                    <td>
                        ${escapeHtml(
                            item.sku || "-",
                        )}
                    </td>

                    <td>
                        ${formatInt(
                            item.available,
                        )}
                    </td>

                    <td>
                        ${formatInt(
                            item.locations,
                        )}
                    </td>

                </tr>
            `,
        )
        .join("");

    content.innerHTML = `

        <div class="grid">

            ${metricCard(
                "Available units",
                formatInt(
                    summary.total_available,
                ),
            )}

            ${metricCard(
                "Inventory items",
                formatInt(
                    summary.inventory_items,
                ),
            )}

            ${metricCard(
                "Locations",
                formatInt(summary.locations),
            )}

            ${metricCard(
                "Out-of-stock levels",
                formatInt(
                    summary.out_of_stock_levels,
                ),
            )}

        </div>


        <div class="section-title">
            Low stock ≤
            ${state.threshold} units
        </div>


        <div class="notice">
            Returned:
            <strong>
                ${data.returned}
            </strong>

            ${
                state.search
                    ? `· Search:
                <strong>
                    ${escapeHtml(state.search)}
                </strong>`
                    : ""
            }
        </div>


        <div class="table-wrap">

            <table>

                <thead>
                    <tr>
                        <th>Product</th>
                        <th>SKU</th>
                        <th>Available</th>
                        <th>Locations</th>
                    </tr>
                </thead>

                <tbody>
                    ${
                        rows ||
                        `
                        <tr>
                            <td colspan="4">
                                No matching inventory.
                            </td>
                        </tr>
                        `
                    }
                </tbody>

            </table>

        </div>
    `;
}
