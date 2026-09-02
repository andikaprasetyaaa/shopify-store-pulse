# 05 · Dashboard Guide

Every visible label, page by page: what it says, what it means, and how
it is calculated. If you only read one document in this folder, read this
one.

---

## Chrome that appears on every page

### Sidebar

| Element | Meaning |
| --- | --- |
| **Shopify / Store Pulse** | Branding. |
| **Nav buttons** | Overview · Inventory · Funnel · Signals · Forecast · Analyst · Data. The active page is highlighted. |
| **Page-specific filters** | Changes with the page. Pages without filters show "No page-specific filters." |
| **Appearance: Light / Dark / Auto** | Colour theme. **Auto** is the default and stores nothing, so it follows the operating system. Light and Dark are remembered in `localStorage`. |
| **Refresh dashboard** | Re-reads the data and redraws the page. |
| **"Refresh reads DuckDB again. It does not call Shopify."** | Literal and important: refreshing gives you the newest *stored* data, never newer data from Shopify. New Shopify data arrives only via the hourly sync. |

### Header

| Element | Meaning |
| --- | --- |
| **Commerce intelligence** | Section eyebrow. |
| **Page title** | The current page's name. |
| **Page description** | One line describing the page's purpose (listed per page below). |
| Chip **Read-only** | A permanent reminder that this app can only read from Shopify. |
| Chip **Orders: `date → date`** | The date span of orders stored in the database — the oldest and newest order dates. |
| Chip **Orders stored: `N`** | How many order rows exist in DuckDB. |

### Status messages you may see

| Message | Meaning |
| --- | --- |
| **Loading...** | The page is fetching from the API. |
| **N/A** | The value does not exist in the data — not zero, but absent. |
| A red **error** box | The API returned an error; the text is the message. |
| **"Production DuckDB does not exist. Run scripts.sync_data first."** | No database yet. Run the sync. |

---

## Page 1 · Overview

> *"Sales momentum, inventory health and active anomaly signals."*

**Sidebar filter — Reporting window:** Last 7 / 14 / 30 / 60 days.
Default 30.

### Top notice bar

| Text | Meaning |
| --- | --- |
| **Requested: `N` days** | The window you selected. |
| **Available: `N` days** | How many days actually exist in the data. If this is smaller than Requested, the store simply has not been syncing that long. |
| **Range: `start → end`** | The actual first and last day being summarised. |

### Hero tiles (the four with ± percentages)

The large tile is Revenue; the others are ordinary stat tiles. Only one
figure is allowed to lead.

| Tile | Meaning | Calculation |
| --- | --- | --- |
| **Revenue · `CURRENCY`** | Total revenue in the window, shown compactly (e.g. `1.2M`). The currency code comes from the orders themselves. | `SUM(orders.total_price)` excluding cancelled orders |
| **Orders** | Number of orders in the window. | `COUNT(orders)` excluding cancelled |
| **AOV** | Average order value. | `revenue ÷ orders` |
| **Units sold** | Total item quantity sold. | `SUM(order_line_items.current_quantity)` |

**The ± percentage under each tile** compares this window against the
immediately preceding window of the same length. Green/up is growth,
red/down is decline. It is **absent** when there is no complete preceding
window of the same length, or when the previous value was zero
(dividing by zero has no meaningful answer).

### Section: Store health

| Tile | Meaning | Watch out for |
| --- | --- | --- |
| **Available stock** | Total sellable units across every location, from the newest inventory snapshot. | It is a total unit count, not a value in money. |
| **Out-of-stock levels** | Count of item-location pairs with zero available. | Counts **pairs, not products**. One variant out of stock at 3 of 5 locations adds 3 and is still sellable elsewhere. |
| **Inventory items** | Number of stock-tracked records in the snapshot. | Roughly the size of your sellable catalogue. |
| **Conversion rate** | Share of sessions that converted, from the ShopifyQL funnel. Shows **N/A** if no funnel snapshot exists. | This comes from a *different dataset* than the revenue tiles, with its own freshness. |

### Section: Sales momentum

Two charts. Both support a hover crosshair with a tooltip, keyboard
navigation (focus the plot, then arrow keys), and a **Table** toggle that
shows the same values as text.

**Chart 1 — Revenue**
*"Daily revenue in `CURRENCY` against its trailing 7-day mean"*

| Series | Meaning |
| --- | --- |
| **Revenue** (solid) | Actual revenue each day. |
| **7-day mean** (dashed) | For each day, the average of the 7 days before it. It is the smoothed trend. |

Read it as: the solid line is the noise, the dashed line is the
direction. The solid line crossing below the dashed line and staying
there is a genuine decline, not a bad day.

The dashed line only starts on the 8th day of the series — before that
there are not 7 prior days to average.

**Chart 2 — Orders**
*"Orders placed per day"* — one bar per day, cancelled orders excluded.

### Section: Signals

The same anomaly cards as the Signals page, embedded here so the
Overview stands alone. See Page 4 below for how to read a card.

---

## Page 2 · Inventory

> *"Explore latest stock availability and identify low-stock variants."*

**Sidebar filters:**

| Filter | Meaning |
| --- | --- |
| **Low-stock threshold** | Show variants with available quantity at or below this number. Default 5. |
| **Search product / SKU** | Free-text filter over product title and SKU. |

### Summary tiles

| Tile | Meaning |
| --- | --- |
| **Available units** | Total sellable units across all locations in the newest snapshot. |
| **Inventory items** | Stock-tracked records in that snapshot. |
| **Locations** | How many distinct locations appear in it. |
| **Out-of-stock levels** | Item-location pairs at zero. |

### Section: "Low stock ≤ `N` units"

`N` is your threshold. The notice line under it reads:

| Text | Meaning |
| --- | --- |
| **Returned: `N`** | Rows shown after the threshold and search filters. It is capped (default 200, maximum 1000), so a large number here can mean "there is more than this". |
| **Search: `text`** | Appears only when a search term is active. |

### The table

| Column | Meaning |
| --- | --- |
| **Product** | Product title. |
| **SKU** | Your stock code, or `-` when the variant has none. |
| **Available** | Units still sellable. |
| **Locations** | How many locations this item is stocked at. A low number here plus low availability is the riskiest combination. |

**"No matching inventory."** means the filters matched nothing — usually
good news, since this is a low-stock table.

---

## Page 3 · Funnel

> *"Monitor sessions, checkout progression and conversion."*

No sidebar filters. This page always shows **the most recent day** in the
most recent ShopifyQL `sessions_daily` snapshot — it does not follow the
Overview's reporting window.

If no snapshot exists you get: **"ShopifyQL funnel snapshot is not
available."** That means the sync has not stored session analytics yet,
or the `read_reports` scope is missing.

### Summary tiles

| Tile | Meaning |
| --- | --- |
| **Sessions** | Visits to the store that day. |
| **Visitors** | Distinct people. Always ≤ Sessions. |
| **Conversion** | Share of sessions that converted, as reported by Shopify. Displayed, not recomputed. |
| **Completed checkout** | Sessions that finished paying. |

### Section: "Session → checkout funnel"

Four bars, each labelled with its count and its **share of Sessions**
(not of the previous stage):

| Stage | Meaning |
| --- | --- |
| **Sessions** | Everyone who arrived. Always 100.0% — it is the denominator. |
| **Cart additions** | Sessions where something was added to a cart. |
| **Reached checkout** | Sessions that opened checkout. |
| **Completed checkout** | Sessions that paid. |

**How to read it:** find the biggest gap between two consecutive bars.
That gap is where you are losing the most people, and it points at
different problems:

- Sessions → Cart additions: product, price, or page experience.
- Cart additions → Reached checkout: shipping cost or trust.
- Reached checkout → Completed checkout: payment methods or checkout
  errors — usually the most urgent, because intent was already there.

The bars use one blue ramp from light to dark, not four different
colours. That is deliberate: the stages are one narrowing flow, and four
categorical hues would imply four unrelated things.

---

## Page 4 · Signals

> *"Review downside anomalies against rolling baselines."*

No sidebar filters. One card per monitored metric: revenue, orders, aov,
units_sold.

### Anatomy of a signal card

| Line | Meaning |
| --- | --- |
| **Metric name** | Which metric this card judges (underscores shown as spaces). |
| **Large value** | The metric's value on the most recent day with data. Money metrics are formatted with the currency. |
| **`7d baseline: X · Y%`** | The average of the previous 7 days, and how far the current value deviates from it. `N/A` means there was not enough history. |
| **Severity badge** | `NORMAL ●` / `WARNING △` / `CRITICAL ▲` / `INSUFFICIENT_DATA ○`. |
| **Reason** | A sentence explaining the verdict in words. |

### Thresholds

| Drop vs baseline | Severity |
| --- | --- |
| under 15% | `NORMAL` |
| 15% – 30% | `WARNING` |
| over 30% | `CRITICAL` |

Only **downside** is flagged. A 200% jump in revenue produces `NORMAL`,
because this engine is an alarm, not a scoreboard.

### The morning trap — read this before acting

Signals score **the most recent day present in the data**. During trading
hours that is a part-day being compared against a baseline of whole days,
so early in the day almost everything reads as a large drop. That is an
artefact of the clock, not a business event.

Rules of thumb:

- Before the day is over, treat CRITICAL on today as "check again later".
- Cross-check with the Overview chart: a real decline shows up as several
  days below the trailing mean, not one part-day.
- The AI analyst is warned about exactly this via an `anomaly_caveat` in
  its context, which is why it may hedge on today's anomalies.

**"No anomaly data available."** means the anomaly engine returned
nothing — usually too few days of history.

---

## Page 5 · Forecast

> *"Short-horizon demand forecast, scored against a seasonal naive
> benchmark."*

**Sidebar filters:** metric (**orders** or **revenue**) and horizon
(1–14 days).

### Summary tiles

| Tile | Meaning |
| --- | --- |
| **Model** | The deployed model, normally `damped_trend`: a day-of-week profile plus a trend that fades as it extends. |
| **Horizon** | How many days ahead are being predicted. |
| **Next day** | Tomorrow's predicted value — the single most actionable number on the page. |
| **History used** | How many days of history fed the model. Today is excluded, because a half-finished day would read as collapsing demand. |

### The accuracy banner

This is not decoration. It is what lets you judge the forecast instead of
trusting it.

| Text | Meaning |
| --- | --- |
| **Rolling-origin backtest over `N` folds** | The model was tested `N` times on the past, each time predicting forward from a cut point without seeing beyond it. |
| **Model MAPE `X%`** | Average error of the deployed model. Lower is better. |
| **vs seasonal_naive `Y%`** | Average error of the benchmark ("same weekday last week"). |
| **"beats the benchmark by `Z%`"** | The model is genuinely adding value at this horizon. |
| **"does not beat the benchmark (`−Z%`)"** | It is not. Reported plainly rather than hidden — at longer horizons the benchmark does catch up, and you are better off knowing. |
| **"Not enough history to backtest this horizon, so no accuracy is reported."** | The store has too few days to score this horizon. Treat the forecast as indicative only. |

### The chart

| Series | Meaning |
| --- | --- |
| **Actual** (solid) | Observed history. |
| **Forecast** (dashed) | Predictions. It starts on the last actual point so the two lines meet instead of leaving a visual gap. |
| **80% band** (shaded) | The uncertainty range: roughly 8 of 10 actual days should land inside it. |

### The prediction table

| Column | Meaning |
| --- | --- |
| **Day** | The predicted date. |
| **Predicted** | The central estimate. |
| **80% band** | Lower – upper bound for that day. |

The band widens with distance. Use the **Predicted** column for planning
and the **band** for how much slack to leave. A band twice as wide as the
prediction is the model telling you it does not really know.

---

## Page 6 · Analyst

> *"A conversation with Gemini about this store. It reads the dashboard's
> own numbers and never computes new ones."*

This is the one page that drops the hero header and fills the window: a
conversation whose composer scrolls off the screen is not usable. The
sidebar stays, because switching pages and changing the reporting window
are both still part of using it.

**Sidebar filter:** the same **Reporting window** as Overview — because
that window decides what data is sent to the model.

| Element | Meaning |
| --- | --- |
| **Store Pulse Analyst** (top bar) | The conversation header. Under it: the model, the reporting window, and the last order date the answers are based on. |
| **New chat** | Clears the conversation and starts fresh. The model then has no memory of what came before. |
| **Preset buttons** | Four openers on the empty screen: **Explain current state**, **Biggest risk**, **Read the forecast**, **Inventory exposure**. |
| **Composer** | The question box. Enter sends, Shift+Enter adds a line. It grows with your question up to a ceiling, then scrolls. |
| Three animated dots | The model is thinking. They occupy the place the answer will appear, so nothing jumps when the text arrives. |
| Line under an answer | **cached** when it was served from cache, and **with N earlier turns** when the model was given the conversation so far. |

### The conversation has a memory

The transcript is sent back with every question, so follow-ups work:
ask *"why?"*, *"which product?"* or *"say more"* and the model knows what
you are referring to.

Three things follow from how that is implemented:

- **The browser holds the conversation, not the server.** The API is
  stateless. Reloading the page starts a new conversation; switching to
  Inventory and back does not.
- **Only the last 20 turns travel.** A long session keeps its recent
  thread rather than being refused.
- **The data snapshot rides on every question, but only once.** Earlier
  turns carry their text alone. Repeating a 30 kB JSON block on each turn
  would cost more with every question and hand the model several stale
  copies of the same figures.

### The answer changes shape with the question

A substantial question — the openers above, or the first question of a
conversation — gets the full six-heading report:

| Heading | Content |
| --- | --- |
| **Summary** | The single most important finding. |
| **Evidence** | The metrics that support it. |
| **Likely explanation** | The most plausible interpretation, hedged ("likely", "suggests") when causality is not proven. |
| **Forecast** | The supplied forecast and its uncertainty — values are never altered. |
| **Priority** | What deserves attention first. |
| **Recommended investigation** | What to inspect next. Analysis only, never a change to Shopify. |

A short follow-up gets a short answer instead: a sentence or a paragraph,
no headings, no restatement of the whole analysis. The discipline is
unchanged — no invented numbers, no altered forecasts, and claims still
labelled. Only the length adapts.

### Three labels the model uses

| Label | Meaning |
| --- | --- |
| **OBSERVED** | Calculated directly from Shopify data. Trust it as fact. |
| **FORECAST** | Produced by the forecasting model. An estimate. |
| **INFERENCE** | The model's interpretation. Not a fact — verify before acting. |

### If it is unavailable

**"The analyst is not configured."** means no `GEMINI_API_KEY` is set.
The rest of the dashboard is unaffected — this feature degrades on its
own.

---

## Page 7 · Data

> *"Inspect DuckDB synchronization and stored data coverage."*

This is the trust page. Read it first whenever a number looks wrong.

### Summary tiles

| Tile | Meaning |
| --- | --- |
| **Orders** | Order rows stored. |
| **Product variants** | Variant rows stored. |
| **Inventory items** | Items in the newest snapshot. |
| **Order range** | Oldest → newest order date. Expect roughly a 60-day span; that is the Shopify scope limit, not missing data. |

### Section: Sync status

Three independent clocks:

| Row | Meaning |
| --- | --- |
| **Orders** | When order rows were last fetched. |
| **Inventory** | The timestamp of the newest stock snapshot. |
| **ShopifyQL** | When the sales/sessions analytics were last stored. |

If one lags far behind the others, only the pages fed by that dataset are
stale. A ShopifyQL clock stuck yesterday means the **Funnel** page is
showing yesterday while the Overview is current.

### Section: DuckDB tables

Row counts per table — `products`, `product_variants`, `inventory_items`,
`inventory_snapshots`, `orders`, `order_line_items`,
`analytics_snapshots`, `analytics_snapshot_rows`.

A count that stops growing between syncs points at a collector that
failed while the rest of the run succeeded.

---

## Number formatting conventions

| Format | Where | Example |
| --- | --- | --- |
| Compact | Large counts and hero revenue | `1.2M`, `45.3K` |
| Integer with separators | Counts | `5,432` |
| Money | AOV, money signals, revenue forecasts | `IDR 125,000.00` |
| Percentage | Conversion, deviation, MAPE | `2.4%` |
| Date | Days on charts and tables | `2026-09-01` |
| `N/A` | The value is **absent**, which is not the same as zero | |

---

Next: [06 · Metrics & Formulas](06-metrics-and-formulas.md)
