# Shopify Store Pulse — Documentation

This folder documents **meaning and context**. It does not replace the
root `README.md`, which covers commands and setup.

If the root README answers *"how do I run it"*, `docs/` answers:

- **why** this application exists,
- **which business process** it is photographing,
- **what every label and number on the dashboard means**,
- **where each number comes from** and **how it is calculated**,
- **what you may and may not conclude** from it.

---

## Suggested reading order

Business readers: 01 → 02 → 04 → 05 is enough.
Engineers: continue with 03 → 06 → 07 → 08.

| # | Document | What it covers | Audience |
| --- | --- | --- | --- |
| 01 | [Background](01-background.md) | The problem, the read-only stance, the 60-day limit | Everyone |
| 02 | [Business Process](02-business-process.md) | The store's operating cycle and how the dashboard maps onto it | Everyone |
| 03 | [Data Flow](03-data-flow.md) | Shopify → DuckDB → API → screen, end to end | Engineers |
| 04 | [Glossary](04-glossary.md) | Funnel, AOV, baseline, anomaly, MAPE, and the rest | Everyone |
| 05 | [Dashboard Guide](05-dashboard-guide.md) | Every label on every page, word by word | Everyone |
| 06 | [Metrics & Formulas](06-metrics-and-formulas.md) | Exact definition and SQL behind each metric | Analysts, engineers |
| 07 | [Technical Architecture](07-architecture.md) | Modules, DuckDB tables, API endpoints | Engineers |
| 08 | [Operations](08-operations.md) | Hourly sync, scheduling, logs, troubleshooting | Engineers, ops |
| 09 | [The AI Analyst](09-ai-analyst.md) | How it works, its behavioural contract, its limits | Everyone |

---

## One-paragraph summary

Store Pulse pulls **read-only** data from the Shopify Admin GraphQL API
(orders, products, inventory, and ShopifyQL session analytics), stores it
in DuckDB once an hour, and serves it through FastAPI to a TypeScript
dashboard with seven pages: **Overview, Inventory, Funnel, Signals,
Forecast, Analyst, Data**. No path in this application can change
anything in Shopify — the client rejects GraphQL mutations before a
request is ever sent.
