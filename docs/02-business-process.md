# 02 · Business Process

## The commerce cycle being measured

Every online store runs the same loop. Store Pulse instruments each
stage of it:

```
   TRAFFIC          BEHAVIOUR             TRANSACTION          SUPPLY
      │                  │                     │                  │
  a visitor  →   browses, adds to  →   pays and the   →   stock is
  arrives         cart, starts          order exists       consumed
      │            checkout                  │                  │
      ▼                  ▼                     ▼                  ▼
  Sessions        Cart additions          Orders            Available
  Visitors        Reached checkout        Revenue           units
                  Completed checkout      AOV / Units       Out of stock
      └──────── FUNNEL page ────────┘     └── OVERVIEW ──┘  └ INVENTORY ┘

              everything above, watched over time
              ────────────────────────────────────
              SIGNALS  (is today abnormal?)
              FORECAST (what does the next week look like?)
              ANALYST  (explain all of the above in words)
              DATA     (can I trust what I am reading?)
```

Each dashboard page answers one question in that loop:

| Page | Business question it answers |
| --- | --- |
| **Overview** | How is the store performing right now, versus the period before it? |
| **Funnel** | Where in the buying journey are visitors dropping off? |
| **Inventory** | What can we still sell, and what is about to run out? |
| **Signals** | Is anything abnormal today, and how badly? |
| **Forecast** | What demand should we prepare for over the next 1–14 days? |
| **Analyst** | Explain the above in plain language, with evidence. |
| **Data** | How fresh and how complete is the data behind all of it? |

---

## The daily operating routine

The dashboard is built for a short, repeatable review. A practical
sequence:

**1 · Trust check (30 seconds) — Data page**

Look at the three sync timestamps: Orders, Inventory, ShopifyQL. If the
newest one is many hours old, the sync is stuck and everything else on
the dashboard is stale. Stop and fix that first.

**2 · Health check (1 minute) — Overview**

Read the four hero tiles and their deltas. The delta compares the
selected window against the immediately preceding window of the *same
length*, so "Last 7 days" is compared against the 7 days before it.
Then glance at the Signals grid at the bottom of the same page.

**3 · Diagnose (as needed) — Signals → Funnel → Inventory**

If revenue is down, the next question is always *where*:

- **Signals** tells you which metric moved and by how much versus its
  7-day baseline.
- **Funnel** separates a traffic problem (fewer sessions) from a
  conversion problem (same sessions, fewer completed checkouts).
- **Inventory** catches the third common cause: the product people
  wanted is out of stock.

**4 · Plan (weekly) — Forecast**

Use the forecast to decide restocking and staffing for the coming days,
and read the accuracy note before trusting it — see below.

**5 · Narrate (optional) — Analyst**

Ask the AI analyst to write up what you just read. It sees exactly the
same numbers the screen does and is not allowed to invent any.

---

## Reading the funnel as a business process

The funnel is the conversion process expressed as four narrowing steps:

| Stage | Business meaning | Typical cause when it drops |
| --- | --- | --- |
| **Sessions** | Someone opened the store | Ad spend paused, SEO drop, campaign ended, seasonality |
| **Cart additions** | The product interested them enough to add | Pricing, product photos, stock availability, page speed |
| **Reached checkout** | They intended to buy | Shipping cost shown late, weak trust signals, forced account creation |
| **Completed checkout** | Money actually moved | Payment gateway failure, limited payment methods, checkout errors |

Each stage is shown with its share of **Sessions** (the first stage), not
of the stage before it. So "Reached checkout 4.0%" means 4% of all
sessions reached checkout. The biggest gap between two consecutive bars
is where you should look first.

---

## Reading signals as an operating alarm

`analytics/anomalies.py` is deliberately **one-directional**: it flags
downside only. Growth is never an alert. The logic:

1. Take the metric's value on the most recent day with data.
2. Compare it to the average of the previous 7 days (today excluded from
   the baseline).
3. Classify the shortfall:

| Drop vs 7-day baseline | Severity | What it usually means operationally |
| --- | --- | --- |
| under 15% | `NORMAL` | Ordinary daily variation. Do nothing. |
| 15% – 30% | `WARNING` | Worth a look today. Check the funnel and stock. |
| over 30% | `CRITICAL` | Investigate now. Something is likely broken or a campaign ended. |
| not enough history | `INSUFFICIENT_DATA` | Not a verdict. The store simply has too few days stored yet. |

The thresholds (15% and 30%) are the defaults in
`analytics/anomalies.py` and are configurable in code, not in the UI.

---

## Reading the forecast responsibly

The forecast exists to support ordering and staffing decisions over
**1–14 days**, no further. Two rules built into the product:

- A model is only deployed if it **beats a seasonal naive benchmark**
  ("this Tuesday will look like last Tuesday") in a rolling-origin
  backtest. The deployed model is `damped_trend`.
- The horizon is capped at 14 days because backtests on this store show
  the model's advantage disappearing around day 11. Offering 30 days
  would be selling certainty that does not exist.

The accuracy banner on the Forecast page reports both MAPE values —
model and benchmark — and states plainly when the model does *not* win.
Read it before acting on the numbers.

---

Next: [03 · Data Flow](03-data-flow.md)
