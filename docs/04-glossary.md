# 04 · Glossary

Every term that appears on screen or in the code, in plain language.
Grouped by area rather than alphabetically, because related terms only
make sense next to each other.

---

## Commerce and funnel terms

### Funnel
A picture of the buying journey as a series of narrowing steps. It is
called a funnel because every stage has fewer people than the one before
it: many visitors look, fewer add to cart, fewer still pay. Its value is
not the absolute numbers but **where the biggest drop happens** — that is
the stage worth fixing.

Store Pulse uses four stages: Sessions → Cart additions → Reached
checkout → Completed checkout.

### Session
One visit to the store. A single person visiting three times in a day
produces three sessions. This is the funnel's denominator.

### Online store visitors
Distinct people, not visits. **Visitors ≤ Sessions**, always. A large gap
between the two means people are coming back repeatedly.

### Cart addition (`sessions_with_cart_additions`)
Sessions in which at least one product was added to the cart. Counted per
session, not per item — adding five products in one visit is still one
session with cart additions.

### Reached checkout (`sessions_that_reached_checkout`)
Sessions that opened the checkout page. This is the point of clear
purchase intent.

### Completed checkout (`sessions_that_completed_checkout`)
Sessions that finished paying. This is the funnel stage closest to an
order, though it will rarely match the order count exactly — they come
from two different Shopify datasets measured in different ways.

### Conversion rate
The share of sessions that ended in a purchase. Supplied by Shopify in
the `sessions` dataset; Store Pulse displays it, it does not recompute
it.

### Revenue
Total money from orders in the period. Here it is the sum of
`orders.total_price`, excluding cancelled orders. It is gross order
value — not profit, and refunds are not deducted.

### Orders
The number of orders placed in the period, cancelled orders excluded.

### AOV — Average Order Value
`revenue ÷ orders`. The average spend per order. AOV rising while orders
fall means fewer but bigger baskets; the reverse means the store is
attracting cheaper purchases.

### Units sold
Total item quantity across those orders, summed from
`order_line_items.current_quantity`. "Current" matters: it reflects the
quantity as it stands now, after edits or removals — so it is closer to
what was actually shipped than the originally ordered quantity.

---

## Time-comparison terms

### Reporting window
The period the Overview page summarises: 7, 14, 30, or 60 days, chosen in
the sidebar.

### Period-over-period (the ± percentages)
Each hero tile compares the selected window against the **immediately
preceding window of the same length**. Pick "Last 7 days" and it is
compared against the 7 days before that. The comparison is skipped
entirely (shown as nothing) if the store does not have a full preceding
window of the same length — a partial comparison would look like a
collapse.

### Baseline
The "normal" a value is judged against. Store Pulse's primary baseline is
`avg_7d`: the average of the previous 7 calendar days. Baselines
**always exclude the day being scored**, otherwise a metric would be
compared against itself.

Other baselines exist in `analytics/baseline.py` and are available to the
code even where the UI does not show them: `avg_14d`, `avg_28d`,
`previous_period_7d_avg` (days −14 to −8), and `same_weekday_4w_avg`
(the same weekday at −7, −14, −21, −28 days).

### Trailing 7-day mean (`baseline_7d` on the revenue chart)
A rolling average: for each day, the mean of the 7 days before it. It
smooths daily noise so the direction of the trend is visible. It only
starts from the 8th day of the series, because before that there are not
7 prior days to average.

### Deviation
How far today sits from its baseline, as a percentage:
`(current − baseline) ÷ baseline × 100`. Negative means below normal.

---

## Anomaly terms

### Anomaly
A value far enough from its baseline that it is unlikely to be ordinary
variation. In Store Pulse anomalies are **downside only** — growth is
never flagged as an alert.

### Severity
The verdict attached to a signal:

| Value | Glyph | Meaning |
| --- | --- | --- |
| `NORMAL` | ● | Within the ordinary range |
| `WARNING` | △ | Down 15–30% versus baseline |
| `CRITICAL` | ▲ | Down more than 30% versus baseline |
| `INSUFFICIENT_DATA` | ○ | Not enough history to judge — an absence of a verdict, not a good one |

The glyphs exist so severity is legible without relying on colour alone.

### Direction
`UP`, `DOWN`, `FLAT`, or `UNKNOWN` — which way the metric moved against
its baseline.

### Reason
A generated sentence explaining the verdict, shown at the bottom of each
signal card. It states the comparison in words rather than making the
reader re-derive it from the numbers.

---

## Forecasting terms

### Forecast
An estimate of future values from past ones. Here: 1 to 14 days of daily
orders or revenue.

### Horizon
How many days ahead the forecast reaches. Capped at 14 — see
[02 · Business Process](02-business-process.md) for why.

### Model
The rule that turns history into a prediction. Five are implemented in
`analytics/forecast.py`:

| Model | Rule |
| --- | --- |
| `naive` | Tomorrow equals today |
| `mean_7` | Flat average of the last 7 days |
| `seasonal_naive` | Each day equals the same weekday last week — **the benchmark** |
| `weekday_profile` | A recent level multiplied by a day-of-week factor |
| `damped_trend` | Weekday profile plus a fading linear trend — **the deployed model** |

### Benchmark
The model a candidate has to beat before it is worth deploying. Here it
is `seasonal_naive`. It is a deliberately dumb rule, which is exactly
what makes it a fair bar: a complicated model that cannot beat "same
weekday last week" is adding nothing.

### Damping (in `damped_trend`)
A trend extrapolated straight out of 60 days of a growing store runs away
quickly. Damping keeps only 85% of the previous step's increment at each
step ahead, so the trend contributes early and fades out. It is a
deliberate brake against over-optimistic forecasts.

### MAPE — Mean Absolute Percentage Error
Average forecast error as a percentage of the actual value. **Lower is
better.** MAPE 20% means predictions were off by about 20% on average.
It is used instead of a raw error because it is comparable across
metrics: 20% is 20% whether you are forecasting orders or rupiah.

### Backtest (rolling-origin)
Testing the model on the past as if the future were unknown. The history
is cut at a point, the model predicts forward from there, and the
prediction is scored against what actually happened. The cut point then
rolls forward and the process repeats. The model never sees data past
its own cut, so there is no leakage.

### Fold
One of those cut points. "8 folds" means the exercise was repeated at
eight different origins and the errors averaged.

### 80% band (prediction interval)
The shaded range around the forecast line. It is derived from the spread
of the model's own backtest residuals: roughly, 8 out of 10 actual days
should land inside it. A wide band is not a bug — it is the model
honestly reporting that this history does not support a precise number.

---

## Inventory terms

### Product / Variant
A product is the listing ("Cotton Shirt"). A variant is the sellable
version of it ("Cotton Shirt / L / Navy"). Stock lives at the variant
level, never at the product level.

### SKU — Stock Keeping Unit
Your internal code for a variant. It may be empty, which is why the table
shows `-` in that case.

### Inventory item
The stock-tracking record attached to a variant. One variant, one
inventory item.

### Location
A physical or logical place stock is held: warehouse, store, third-party
fulfilment.

### Inventory level
The quantity of **one inventory item at one location**. This is the
atomic unit of stock: one variant stocked in three warehouses is three
inventory levels.

### Available
Units on hand that can be sold — not committed to unfulfilled orders and
not damaged.

### Out-of-stock levels
The count of inventory levels where `available = 0`. Read it carefully:
it counts **item-location pairs, not products**. One variant that is out
of stock in three of five locations contributes 3 — and is still sellable
from the other two. It is an early-warning signal about distribution, not
a count of dead products.

### Low-stock threshold
The sidebar number that decides which variants appear in the Inventory
table. Default 5: show everything at 5 units or fewer.

### Inventory snapshot
A full photograph of every inventory level at one point in time. Store
Pulse stores one per day by default (see the bucket discussion in
[03 · Data Flow](03-data-flow.md)).

---

## Data and infrastructure terms

### Shopify Admin GraphQL API
The interface Store Pulse reads from. GraphQL means the caller asks for
exactly the fields it needs in one request instead of fetching whole
objects from several REST endpoints.

### ShopifyQL
Shopify's own query language for its analytics datasets. Store Pulse runs
two queries against it, both over the last 60 days:

- `FROM sales` → `sales_daily`
- `FROM sessions` → `sessions_daily` (this is what feeds the Funnel page)

### Scope
A permission granted to the app. All of Store Pulse's are `read_*`.

### Client credentials grant
Obtaining an access token at runtime from a client id and secret, instead
of storing a long-lived token in a file. The token is refreshed before it
expires; nothing sensitive is committed.

### Cursor pagination
Shopify returns large result sets in pages, each carrying a cursor
pointing at the next one. `shopify/pagination.py` follows those cursors
until the data is exhausted.

### DuckDB
An embedded analytical database — a single file, no server process, fast
at aggregation. Ideal here, with one hard constraint: **one writer or
many readers, never both.**

### Snapshot / bucket / retention
A **snapshot** is a point-in-time capture. The **bucket** rounds its
timestamp down (to the day by default) so repeated runs in the same
bucket overwrite rather than accumulate. **Retention** deletes snapshot
rows older than N days (default 30).

### Upsert (`INSERT OR REPLACE`)
Insert a row, or overwrite it if its primary key already exists. This is
what makes the sync safe to re-run: rerunning it never duplicates rows.

### Incremental sync
Fetching only what changed. Orders are fetched by
`updated_at:>= <newest stored update − 90 minutes>`; the overlap window
guards against rows landing exactly on the boundary.

### Serving copy
The read-only duplicate (`data/serving.duckdb`) published after each
successful sync, so readers never contend with the writer.

### Checkpoint
Flushing DuckDB's write-ahead log into the database file, so the
published copy is complete and self-contained.

---

Next: [05 · Dashboard Guide](05-dashboard-guide.md)
