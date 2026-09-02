# 07 · Technical Architecture

## Repository layout

```
shopify-store-pulse/
├── shopify/          Admin GraphQL client — auth, query(), pagination
│   ├── config.py     credentials and shop slug from .env
│   ├── client.py     client credentials grant; query() only, no mutations
│   ├── queries.py    the GraphQL documents, incl. RunShopifyQL
│   └── pagination.py cursor paging helper
│
├── collectors/       fetch and shape; no business logic
│   ├── products.py   products + variants
│   ├── inventory.py  inventory items + levels
│   ├── orders.py     orders + line items
│   └── analytics.py  ShopifyQL: sales_daily, sessions_daily
│
├── storage/
│   └── database.py   schema, upserts, pruning, serving-copy publish
│
├── analytics/        the only place numbers are computed
│   ├── metrics.py    daily order metrics, inventory summary, funnel row
│   ├── baseline.py   avg_7d / 14d / 28d, previous period, same weekday
│   ├── anomalies.py  severity classification, downside only
│   └── forecast.py   five models, backtest, residual band
│
├── services/         one module per dashboard payload
│   ├── overview.py   KPIs + comparison + trend + inventory + funnel + signals
│   ├── trends.py     series filling, period summary, trailing mean
│   ├── inventory.py  stock summary + low-stock table
│   ├── funnel.py     latest ShopifyQL session row
│   ├── signals.py    anomaly cards
│   ├── forecast.py   forecast + accuracy for the chart
│   ├── metadata.py   table counts and freshness
│   └── analyst.py    the snapshot handed to Gemini
│
├── api/
│   ├── app.py        FastAPI wiring, static mount, error handlers
│   ├── deps.py       database path resolution, existence guard
│   ├── formatting.py iso_value, percent_change, serialize_anomaly
│   └── routers/      dashboard.py, analyst.py, system.py
│
├── analyst/          Gemini integration
│   ├── config.py     key and model from environment
│   ├── client.py     HTTP call, header auth
│   └── prompt.py     the system prompt and its six sections
│
├── frontend/src/     TypeScript dashboard, built by Vite
│   ├── main.ts       page router, theme switch, header metadata
│   ├── state.ts      shared filter state + page descriptions
│   ├── api.ts        typed fetch wrappers
│   ├── controls.ts   sidebar filters per page
│   ├── charts.ts     SVG charts: crosshair, keyboard, table toggle
│   ├── chart-card.ts the card wrapper around a chart
│   ├── format.ts     number/date formatting, metricCard, escapeHtml
│   ├── theme.ts      light / dark / auto
│   ├── types.ts      payload types mirroring the API
│   └── pages/        overview, inventory, funnel, signals, forecast,
│                     analyst, data
│
├── dashboard/app.py  the separate Streamlit dashboard
├── scripts/          sync, scheduling, and check_* inspectors
├── tests/            pytest, including the read-only boundary suite
└── docs/             this folder
```

---

## Architectural rules

1. **Numbers are computed exactly once**, in `analytics/`. Every consumer
   — API, Streamlit, AI analyst, CLI inspectors — reads the same
   functions, so they cannot disagree.
2. **Routers are thin.** Read query parameters, call a service, return
   what it produces. No `try/except` in a router: errors are translated
   centrally in `api/app.py`.
3. **Collectors never aggregate.** They fetch and shape. Judging is
   somebody else's job.
4. **The frontend never computes a business metric.** It renders and
   formats. The only arithmetic it does is turning a stage value into a
   percentage of sessions for the funnel bars.
5. **The read-only boundary is enforced in the client**, not by
   convention.

---

## DuckDB schema

| Table | Primary key | Contents |
| --- | --- | --- |
| `products` | `product_id` | title, handle, status, vendor, product_type, collected_at |
| `product_variants` | `variant_id` | product_id, title, sku, price, inventory_item_id |
| `inventory_items` | `inventory_item_id` | variant_id, product_id, product_title, sku, tracked |
| `inventory_snapshots` | `(snapshot_at, inventory_level_id)` | item, variant, product, location, `available` |
| `orders` | `order_id` | order_name, created_at, updated_at, cancelled_at, financial/fulfillment status, total_price, currency_code |
| `order_line_items` | `line_item_id` | order_id, product_id, variant_id, sku, quantity, current_quantity, totals |
| `forecast_runs` | `(forecast_at, target_day, metric, model_name)` | horizon, predicted, lower_bound, upper_bound |
| `analytics_snapshots` | `(dataset_name, snapshot_at)` | columns_json, row_count |
| `analytics_snapshot_rows` | `(dataset_name, snapshot_at, row_index)` | row_json |

Design notes:

- **Current-state tables** (`products`, `orders`, …) hold the newest
  version of each row; a re-sync overwrites by primary key.
- **Snapshot tables** hold history keyed by a bucketed timestamp; a
  re-sync inside the same bucket deletes then rewrites, so a shrinking
  catalogue leaves no stale rows behind.
- **ShopifyQL results are stored as JSON**, not as typed columns. The
  dataset's shape is Shopify's to change, and storing the raw rows means
  a schema change does not break the sync. Decoding happens in
  `analytics/metrics.py`.
- **`forecast_runs`** records what was predicted and when, so past
  forecasts can be scored against what actually happened.

---

## API reference

Base URL: `http://127.0.0.1:8000`. Interactive docs: `/docs`.

### Dashboard routes

| Route | Parameters | Returns |
| --- | --- | --- |
| `GET /api/overview` | `days` 1–60, default 30 | KPIs, previous period, change percentages, trend series, inventory summary, funnel row, signals |
| `GET /api/inventory` | `threshold` 0–1000000 (default 5), `search` ≤100 chars, `limit` 1–1000 (default 200) | Stock summary and the low-stock rows |
| `GET /api/funnel` | — | `available` flag plus the latest ShopifyQL session row |
| `GET /api/signals` | — | One anomaly result per metric, plus an `error` field |
| `GET /api/forecast` | `metric` `orders|revenue`, `horizon` 1–14, `history_days` 7–60 | History, predictions with bands, model name, accuracy |
| `GET /api/data-health` | — | Table row counts, order date range, three sync timestamps |

### Analyst routes

| Route | Purpose |
| --- | --- |
| `GET /api/analyst/status` | Whether a Gemini key is configured. The page asks first, so the rest of the dashboard works without one. |
| `POST /api/analyst` | One question, answered over the current data. |

### Error handling

Three exception types are translated centrally into HTTP 500 with a
consistent `{"detail": "..."}` body:

| Exception | Raised when |
| --- | --- |
| `DashboardDataError` | The database does not exist yet |
| `MetricsError` | A metric cannot be computed safely |
| `duckdb.Error` | Any database-level failure, including a lock conflict |

Query parameters are validated by FastAPI itself, so an out-of-range
`days` returns a 422 before any service runs.

---

## Frontend architecture

- **No routing, no history.** Page state is one mutable object in
  `state.ts`. The dashboard is a tool, not a linkable document.
- **`requireElement()` fails loudly.** A renamed id in `index.html`
  surfaces as a visible error instead of a silently blank page.
- **Untrusted text is escaped.** Model output is rendered with
  `textContent` only; nothing user- or model-supplied goes through
  `innerHTML`.
- **Charts redraw on theme change.** They read CSS custom properties with
  `getComputedStyle` at draw time, because an SVG `stroke` is already a
  resolved colour by the time the theme flips — CSS alone cannot
  recolour it.
- **Every chart ships a Table toggle**, a hover crosshair, and keyboard
  navigation. The table is not decoration: it is what keeps every value
  readable without a pointer.

### Colour tokens

The data colours came from a validator, not from taste. They clear
colourblind-separation, chroma, lightness-band and contrast gates in both
themes.

| Role | Light | Dark |
| --- | --- | --- |
| Series 1 (revenue, orders, actuals) | `#2a78d6` | `#3987e5` |
| Series 2 (baseline, forecast, band) | `#eb6834` | `#d95926` |
| Funnel stages | four steps of one blue ramp | the same ramp, re-stepped |

Re-run the check before changing any of these values.

The palette is defined three times in `frontend/src/styles.css`: light on
`:root`, dark under `prefers-color-scheme`, and dark again under
`[data-theme="dark"]` so the in-app switch wins in both directions.

---

## Two dashboards, one database

| Dashboard | Stack | Purpose |
| --- | --- | --- |
| `frontend/` + `api/` | TypeScript + FastAPI | The main product |
| `dashboard/app.py` | Streamlit | A standalone, quicker-to-modify view |

Both read `data/serving.duckdb`. Neither calls Shopify.

---

Next: [08 · Operations](08-operations.md)
