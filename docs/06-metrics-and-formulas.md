# 06 · Metrics & Formulas

The exact definition behind every number, with the code that produces it.
When a figure is questioned, this is the document that settles it.

---

## Universal rules

These apply to every order-derived metric:

1. **Cancelled orders are excluded.** Every query filters
   `cancelled_at IS NULL` (`exclude_cancelled=True` by default in
   `analytics/metrics.py`).
2. **A day means the calendar date of `created_at`**, cast to `DATE` in
   the database's timezone handling.
3. **Missing days are treated as zero**, not skipped. A day with no
   orders is a real zero, and dropping it would inflate averages.
4. **Money is `DECIMAL(18,2)`** through the whole pipeline, converted to
   float only at the moment of rendering. Currency arithmetic is never
   done in floating point.
5. **Only one currency is supported per store.**
   `_single_currency()` resolves it from the orders themselves; a
   multi-currency store would need to be handled explicitly.

---

## Daily order metrics

Produced by `StorePulseMetrics.daily_order_metrics()` in
`analytics/metrics.py`. This one function is the source of Overview,
Signals, and the forecast history — which is why those three can never
disagree.

```sql
WITH filtered_orders AS (
    SELECT order_id, created_at, total_price
    FROM orders
    WHERE cancelled_at IS NULL          -- plus optional date range
),
units_by_order AS (
    SELECT order_id, SUM(current_quantity) AS units_sold
    FROM order_line_items
    GROUP BY order_id
)
SELECT
    CAST(f.created_at AS DATE)                     AS day,
    COUNT(*)                                       AS orders,
    COALESCE(SUM(f.total_price), DECIMAL '0.00')   AS revenue,
    COALESCE(SUM(u.units_sold), 0)                 AS units_sold
FROM filtered_orders AS f
LEFT JOIN units_by_order AS u ON u.order_id = f.order_id
GROUP BY CAST(f.created_at AS DATE)
ORDER BY day ASC
```

| Metric | Formula | Note |
| --- | --- | --- |
| **Revenue** | `SUM(orders.total_price)` | Gross order value. Not profit, refunds not deducted. |
| **Orders** | `COUNT(orders)` | |
| **Units sold** | `SUM(order_line_items.current_quantity)` | `current_quantity`, not the original — it reflects edits and removals. |
| **AOV** | `revenue ÷ orders` | Returns `0` when orders is `0`, never a division error. |

The `LEFT JOIN` matters: an order whose line items are missing still
counts toward revenue and orders, contributing `0` units rather than
vanishing.

---

## Period summary and comparison

`services/trends.py` → `summarize_period()` and
`api/formatting.py` → `percent_change()`.

```
revenue_period    = Σ revenue over the days in the window
orders_period     = Σ orders
units_period      = Σ units_sold
aov_period        = revenue_period ÷ orders_period      (0 if no orders)

change_pct        = (current − previous) ÷ previous × 100
```

Two rules decide whether a `change_pct` is shown at all:

- **Equal lengths only.** The previous period must contain exactly as
  many days as the current one, otherwise no comparison is produced.
  Comparing 30 days against a 12-day remnant would look like a collapse.
- **No division by zero.** If the previous value was `0`, the result is
  `null` and the UI shows nothing.

Note that AOV for a period is computed from the period's totals, **not**
as the average of the daily AOVs. Averaging averages would weight a
quiet Sunday the same as a busy Friday.

---

## Trailing 7-day mean (`baseline_7d`)

`services/trends.py` → `build_trend()`.

```
baseline_7d[i] = mean( revenue[i−7 .. i−1] )     for i ≥ 7
baseline_7d[i] = null                            for i < 7
```

It uses only days **before** day `i` — the current day is never part of
its own baseline. The first 7 days of any series therefore have no
baseline, which is why the dashed line on the revenue chart starts later
than the solid one.

---

## Baselines

`analytics/baseline.py` → `order_metric_baseline()`. Supported metrics:
`revenue`, `orders`, `aov`, `units_sold`.

| Baseline | Window | Answers |
| --- | --- | --- |
| `avg_7d` | previous 7 calendar days | "Normal for this past week" — **the one used for signals** |
| `avg_14d` | previous 14 days | A steadier normal |
| `avg_28d` | previous 28 days | The steadiest available at 60 days of history |
| `previous_period_7d_avg` | days −14 to −8 | Last week's normal, for week-over-week |
| `same_weekday_4w_avg` | −7, −14, −21, −28 days | Normal *for this weekday*, removing the weekly cycle |

Invariants:

- **Baselines always exclude the day being scored.**
- Missing calendar days inside the known range count as zero.
- A baseline is `null` when there is not enough history, and a `null`
  baseline can never produce a WARNING or CRITICAL — it produces
  `INSUFFICIENT_DATA`.

---

## Anomaly detection

`analytics/anomalies.py` → `StorePulseAnomalyEngine`.

```
current   = the metric's value on the most recent day with data
baseline  = avg_7d
deviation = (current − baseline) ÷ baseline × 100
```

Classification (downside only):

| Condition | Severity |
| --- | --- |
| `baseline` is null | `INSUFFICIENT_DATA` |
| `deviation > −15%` | `NORMAL` |
| `−30% < deviation ≤ −15%` | `WARNING` |
| `deviation ≤ −30%` | `CRITICAL` |

Defaults live in the engine as
`DEFAULT_WARNING_THRESHOLD = 15` and
`DEFAULT_CRITICAL_THRESHOLD = 30`, and the constructor validates them:
warning must be greater than zero, and critical must be strictly greater
than warning. Deviations are quantised to two decimals with
`ROUND_HALF_UP` so displayed and stored values agree.

**Positive deviation is never an alert.** The engine is an alarm for
things going wrong, not a scoreboard for things going right.

---

## Inventory metrics

`analytics/metrics.py` → `latest_inventory_summary()`, reading only the
newest snapshot (`MAX(snapshot_at)`).

| Metric | Definition |
| --- | --- |
| `total_available` | Sum of `available` across every inventory level in the snapshot |
| `inventory_items` | Distinct inventory items present |
| `inventory_levels` | Distinct item-location pairs |
| `locations` | Distinct locations |
| `tracked_items` | Items with stock tracking enabled |
| `out_of_stock_levels` | Count of levels where `available = 0` |

The distinction that trips people up: **`out_of_stock_levels` counts
item-location pairs, not products.** A variant out of stock at 3 of 5
locations contributes 3 to this number and is still sellable from the
other two. It is a distribution warning, not a catalogue count.

The low-stock table is a separate query against the same snapshot:
`available <= threshold`, optionally filtered by a case-insensitive
substring of product title or SKU, ordered by availability ascending and
capped by `limit` (default 200, maximum 1000).

---

## Funnel metrics

`analytics/metrics.py` → `latest_funnel_metrics()`.

**This is not computed by Store Pulse.** These figures come from
Shopify's own `sessions` dataset via ShopifyQL:

```sql
FROM sessions
SHOW sessions, conversion_rate,
     online_store_visitors,
     sessions_with_cart_additions,
     sessions_that_reached_checkout,
     sessions_that_completed_checkout
TIMESERIES day
SINCE -60d UNTIL today
ORDER BY day ASC
```

Selection logic: take the newest `snapshot_at` for the `sessions_daily`
dataset, decode its JSON rows, and pick the row with the greatest `day`.
So the page shows **the latest day inside the latest snapshot**.

The stage percentages rendered by the dashboard are:

```
share = stage_value ÷ sessions × 100
```

— each stage against **Sessions**, not against the stage before it.
Sessions is therefore always 100.0%.

Because this comes from a different dataset, `sessions_that_completed_checkout`
will not exactly equal the order count for the same day. They measure
different things and are collected differently; a small gap is expected.

---

## Forecasting

`analytics/forecast.py`. Every model is a pure function of the history
with no fitted state to persist and no third-party dependency.

```
WEEK = 7

naive(h)           = [history[-1]] * h
mean_7(h)          = [mean(history[-7:])] * h
seasonal_naive(h)  = [history[-7 + (i mod 7)] for i in 0..h-1]
weekday_profile(h) = recent_level × weekday_factor[day]
damped_trend(h)    = weekday_profile + fading trend
```

### The deployed model: `damped_trend`

```
base      = weekday_profile(history, horizon)
slope     = (mean(last 7 days) − mean(previous 7 days)) ÷ 7
increment = increment × damping + slope × damping^step      (damping = 0.85)
prediction[step] = max(0, base[step] + increment)
```

Two safeguards are worth naming:

- **Damping (0.85).** A raw trend from 60 days of a growing store runs
  away fast. Keeping only 85% of the previous increment per step lets the
  trend contribute early and fade out.
- **`max(0, …)`.** Predictions can never go negative — negative orders do
  not exist.

If the history is shorter than 14 days, `damped_trend` falls back to the
plain weekday profile, because a slope between two whole weeks cannot be
computed.

### Backtesting

```
for each fold:
    cut         = a point in the history
    predicted   = model(history[:cut], horizon)
    actual      = history[cut : cut+horizon]
    error       = mean(|actual − predicted| ÷ actual) × 100      # MAPE
```

The model never sees data past its cut, so there is no leakage. Scores
are averaged per model across every horizon (`summarize()`), and the
deployed model is compared against `BENCHMARK = "seasonal_naive"`.

### The 80% band

Derived from the spread of the model's own backtest residuals
(`residual_spread()`), so the band reflects how wrong this model has
actually been on this store's data — not a textbook assumption about the
distribution.

### Horizon cap

`MAX_HORIZON = 14` in `services/forecast.py`. Backtests on this store
show the model beating the benchmark up to roughly h+11 and drawing level
after that. Offering 30 days would sell certainty that is not there.

### History selection

```sql
SELECT created_at::DATE AS day, COUNT(*) AS value    -- or SUM(total_price)
FROM orders
WHERE cancelled_at IS NULL
  AND created_at::DATE < CURRENT_DATE
GROUP BY 1
ORDER BY 1
```

`< CURRENT_DATE` is the important line: **today is excluded** because it
is still collecting orders, and feeding a half-finished day to the model
would read as a sudden collapse in demand.

---

Next: [07 · Technical Architecture](07-architecture.md)
