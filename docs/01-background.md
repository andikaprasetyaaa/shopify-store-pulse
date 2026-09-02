# 01 · Background

## The problem this solves

The Shopify admin already shows plenty of numbers. Three things it does
not give you:

1. **Context.** Shopify tells you "today's revenue is X". It does not
   tell you whether X is normal for a Tuesday, or already 30% below last
   week's average.
2. **Automatic warning.** A decline is usually noticed days late,
   because nothing routinely compares today against its own baseline.
3. **Data you can work with.** The built-in reports do not easily
   combine orders, stock, and session traffic into one view.

Store Pulse answers all three: it pulls the raw data on a schedule,
computes baselines and anomalies, and puts everything on one screen.

---

## Core principle: **read-only, no exceptions**

This is the most important design decision in the project, and it is
enforced in layers:

| Layer | How it is enforced |
| --- | --- |
| **App scopes** | The custom app requests `read_*` scopes only. `scripts/check_connection.py` fails if any granted scope starts with `write_`. |
| **GraphQL client** | `shopify/client.py` exposes `query()` and nothing else. Mutations are rejected **before** any network call. |
| **Credentials** | No access token is pasted anywhere. A token is requested at runtime via a client credentials grant and refreshed before it expires. |
| **AI analyst** | The system prompt explicitly forbids recommending any Shopify write operation. |
| **Tests** | `pytest` covers the read-only boundary as its own suite. |

The practical consequence: **this application cannot damage the store.**
The worst misconfiguration produces an empty dashboard, not altered
Shopify data.

Required scopes:

- `read_inventory`
- `read_locations`
- `read_orders`
- `read_products`
- `read_reports`

---

## Constraints you need to know up front

### 1. Order history is only ~60 days

The standard `read_orders` scope exposes a 60-day window. That is a
Shopify limitation, not a design choice. It means:

- **No** yearly seasonality (Ramadan vs Christmas vs mid-year sale).
- **No** year-over-year comparison.
- **Yes** to weekly cycles (Monday vs Saturday) and short-term level
  changes.

This is why every model in `analytics/forecast.py` is deliberately
simple: they model **a level plus a day-of-week pattern**, and nothing
more. The AI analyst's prompt is likewise forbidden from claiming yearly
seasonality.

### 2. Today's numbers are always half-finished

The current day is still collecting orders. Compared naively against
baselines built from complete days, every morning reads as "sales
collapsed 50%". That is a clock artefact, not a business event.

The codebase handles it in two different ways:

- **Forecast** (`services/forecast.py`) drops today from the history:
  `created_at::DATE < CURRENT_DATE`.
- **Signals** (`analytics/baseline.py`) still scores the latest day that
  has data, but the context sent to the AI analyst carries an
  `anomaly_caveat` so the model does not report the artefact as its
  headline finding.

### 3. The funnel comes from a different source

Funnel numbers (sessions, conversion) do **not** come from the orders
tables. They come from ShopifyQL `FROM sessions`, snapshotted
separately. So it is normal for the funnel's latest day to differ from
the orders' latest day — the **Data** page shows all three sync times
side by side.

### 4. The dashboard never calls Shopify

**Refresh dashboard** re-reads DuckDB only. New Shopify data arrives
solely through the hourly sync job. This keeps Shopify's rate limits
safe no matter how many people open the dashboard.

---

Next: [02 · Business Process](02-business-process.md)
