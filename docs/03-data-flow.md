# 03 · Data Flow

## End-to-end picture

```
┌──────────────────────────────────────────────────────────────┐
│ SHOPIFY  (Admin GraphQL API, read-only)                      │
│   products · variants · inventory levels · orders            │
│   ShopifyQL: sales_daily, sessions_daily                     │
└───────────────────────────┬──────────────────────────────────┘
                            │  shopify/client.py  (query only)
                            │  shopify/pagination.py (cursor paging)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ COLLECTORS   collectors/{products,inventory,orders,analytics}│
│   fetch + shape into typed rows. No business logic here.     │
└───────────────────────────┬──────────────────────────────────┘
                            │  scripts/sync_data.py  (hourly)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ WRITE DATABASE   data/shopify_store_pulse.duckdb             │
│   storage/database.py — INSERT OR REPLACE by primary key     │
└───────────────────────────┬──────────────────────────────────┘
                            │  publish_serving_copy()
                            │  copy → .tmp → atomic rename
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ SERVING DATABASE   data/serving.duckdb   (readers only)      │
└───────────────────────────┬──────────────────────────────────┘
                            │  api/deps.py resolve_read_path()
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ ANALYTICS   analytics/{metrics,baseline,anomalies,forecast}  │
│   raw rows → daily metrics → baselines → anomalies/forecast  │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ SERVICES    services/{overview,inventory,funnel,signals,     │
│                       forecast,metadata,trends,analyst}      │
│   assemble the exact JSON payload one page needs             │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ API   api/app.py + api/routers/{dashboard,analyst,system}    │
│   thin routers, central error handling                       │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ FRONTEND   frontend/src/pages/*.ts  →  the seven pages       │
└──────────────────────────────────────────────────────────────┘
                            │
                            └──► services/analyst.py ──► Gemini
                                 (a snapshot of the above, never raw data)
```

---

## Layer responsibilities

The separation is strict, and it is what keeps the codebase testable:

| Layer | Does | Never does |
| --- | --- | --- |
| `shopify/` | Auth, one `query()` entry point, cursor pagination | Business logic, database writes |
| `collectors/` | Fetch and shape API responses into rows | Aggregate, judge, or persist |
| `storage/` | Schema, upserts, pruning, publishing the serving copy | Call Shopify, compute metrics |
| `analytics/` | Aggregate, build baselines, detect anomalies, forecast | Call Shopify, write DuckDB, format for display |
| `services/` | Compose one page's payload from analytics | Contain SQL for its own sake, handle HTTP |
| `api/` | Route, validate query parameters, map errors to HTTP | Contain query logic |
| `frontend/` | Render and format | Compute business metrics |

One rule worth remembering: **numbers are computed exactly once**, in
`analytics/`. The API, the Streamlit dashboard, the AI analyst, and the
`scripts/check_*.py` inspectors all read the same functions, so they
cannot disagree with each other.

---

## Why there are two database files

DuckDB is embedded, not a server: **one writer or many readers, never
both**. The hourly sync holds the write lock for the whole run, so a
dashboard reading the same file would fail for minutes with
`IO Error: Could not set lock on file ...`.

The solution is a publish step:

| File | Written by | Read by |
| --- | --- | --- |
| `data/shopify_store_pulse.duckdb` | `scripts/sync_data.py` only | nothing |
| `data/serving.duckdb` | published at the end of each successful run | `api/app.py`, `dashboard/app.py` |

After the write connection is checkpointed and closed,
`publish_serving_copy()` copies the database to `serving.duckdb.tmp` and
renames it into place. Rename is atomic on the same filesystem, so a
reader sees either the old copy or the new one — never a half-written
file. `resolve_read_path()` prefers the serving copy and falls back to
the live database, so a fresh checkout works before the first sync ever
runs.

`api/deps.py` re-resolves the path **on every request**, which is why a
copy published after the API started is picked up without a restart.

---

## What one sync run actually does

`scripts/run_sync.sh` invokes:

```bash
python -m scripts.sync_data --incremental \
    --snapshot-bucket day --retention-days 30
```

Step by step:

1. **Acquire a PID lock** (`data/*.duckdb.sync.lock`). An overlapping run
   exits with `[SKIP]` instead of colliding on the write lock.
2. **Orders — incremental.** Refetch only orders with
   `updated_at:>= <newest stored update − overlap>` (default overlap: 90
   minutes) instead of all 5k+ orders every hour. Changed orders
   overwrite their rows by primary key.
3. **Products and inventory — always full.** Shopify offers no
   incremental filter for them.
4. **ShopifyQL** — run `sales_daily` and `sessions_daily`, store the
   result as a snapshot with its columns and rows.
5. **Bucket the snapshot timestamp** down to the day (default), so every
   run inside the same bucket replaces the previous one instead of
   stacking another ~72k inventory rows.
6. **Prune** snapshot rows older than 30 days, then checkpoint.
7. **Publish** the serving copy.

The runner retries up to 3 times, 60 seconds apart, which covers the
brief moments a reader connection holds the file.

### Why the day bucket matters

One measured inventory snapshot is 72,260 rows / 5.5 MB:

| `--snapshot-bucket` | Retained per day | Database at 30-day retention |
| --- | --- | --- |
| `day` (default) | 1 snapshot, 5.5 MB | ~0.16 GB |
| `hour` | 24 snapshots, 0.13 GB | ~3.9 GB |

Bucketing does not reduce freshness — the job still runs hourly and still
overwrites with current data every hour. The bucket only controls how
much *history* is kept. Nothing in `analytics/` needs hourly inventory
history today: `metrics.py` reads only the newest snapshot via
`MAX(snapshot_at)`, and anomaly detection works off orders.

---

## Freshness: three independent clocks

The **Data** page shows three timestamps because the three datasets
advance independently:

| Clock | Source column | Meaning |
| --- | --- | --- |
| **Orders** | `MAX(orders.collected_at)` | When order rows were last fetched |
| **Inventory** | `MAX(inventory_snapshots.snapshot_at)` | The bucket of the newest stock snapshot |
| **ShopifyQL** | `MAX(analytics_snapshots.snapshot_at)` | When the sessions/sales datasets were last stored |

If one of them lags far behind the others, only the pages fed by that
dataset are stale — not the whole dashboard.

---

Next: [04 · Glossary](04-glossary.md)
