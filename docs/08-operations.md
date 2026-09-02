# 08 · Operations

Running, scheduling, monitoring and repairing Store Pulse.

---

## Environment

`.env` is never committed; `.env.example` is committed and shows only the
shape:

| Variable | Purpose |
| --- | --- |
| `SHOPIFY_SHOP` | Shop slug |
| `SHOPIFY_CLIENT_ID` | Custom app client id |
| `SHOPIFY_CLIENT_SECRET` | Custom app client secret |
| `SHOPIFY_API_VERSION` | Admin API version, e.g. `2026-07` |
| `GEMINI_API_KEY` | Google AI Studio key for the Analyst page (optional) |
| `GEMINI_MODEL` | Gemini model id. `.env.example` and the live `.env` currently name different models; the running value is the one the Analyst page prints under its answer. |

There is **no access token to paste.** `shopify/client.py` requests one at
runtime with a client credentials grant and refreshes it before it
expires.

---

## First run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill it in

python -m scripts.check_connection    # verify credentials and scopes
python -m scripts.sync_data           # first full sync

cd frontend && npm install && npm run build && cd ..
uvicorn api.app:app --port 8000
```

Open <http://127.0.0.1:8000>.

`check_connection` fails if a required scope is missing **or if any
granted scope starts with `write_`**. Both failures are intentional: the
second one means the app has more power than this project is willing to
hold.

---

## Running

### Normal use — one process

The API serves the built frontend, so a single process is the whole app.

```bash
source .venv/bin/activate
npm --prefix frontend run build      # only after changing frontend/src
uvicorn api.app:app --port 8000
```

OpenAPI docs live at `/docs`.

### Editing the frontend — two processes

```bash
# terminal 1
source .venv/bin/activate
uvicorn api.app:app --reload --port 8000

# terminal 2
npm --prefix frontend run dev
```

Open <http://localhost:5173>. Port 8000 must be the API's, because that
is what `vite.config.ts` proxies to. Note that `:8000` still serves the
last *built* bundle, which is not what you are editing.

### Streamlit dashboard

```bash
streamlit run dashboard/app.py
```

Independent of the above, and reads the same `data/serving.duckdb`.

### Frontend commands

| Command | What it does |
| --- | --- |
| `npm run build` | Type-checks, then writes `frontend/dist` (what FastAPI serves) |
| `npm run typecheck` | `tsc --noEmit` only |
| `npm run dev` | Vite dev server on :5173 with hot reload, proxying `/api` to :8000 |

`frontend/dist` and `frontend/node_modules` are not committed. After
pulling a change to `frontend/src`, re-run `npm run build` or the browser
keeps the old bundle.

---

## The sync job

### Manual run

```bash
python -m scripts.sync_data
```

| Flag | Default | Effect |
| --- | --- | --- |
| `--incremental` | off | Refetch only orders updated since the newest stored update, minus the overlap |
| `--overlap-minutes N` | 90 | Safety window subtracted from the incremental watermark |
| `--snapshot-bucket hour\|day\|exact` | `day` | Rounding applied to snapshot timestamps |
| `--retention-days N` | 30 | Delete snapshots older than N days after a successful run; `0` disables pruning |
| `--forecast-horizon N` | 14 | Days ahead to forecast and store in `forecast_runs` |
| `--skip-products` | off | Skip the full product catalogue sync |
| `--skip-analytics` | off | Skip the ShopifyQL sync |
| `--skip-forecast` | off | Do not write the daily forecast |
| `--no-publish` | off | Skip refreshing the serving copy |
| `--reset` | off | Delete the production database before syncing |

### Scheduled run (macOS launchd)

`scripts/com.storepulse.sync.plist` is **not committed** — it holds
absolute paths specific to the machine it was installed on. Create it
from the template in the root `README.md` before running the installer.

```bash
bash scripts/install_schedule.sh          # install + run once now
bash scripts/install_schedule.sh remove   # uninstall
```

This installs `~/Library/LaunchAgents/com.storepulse.sync.plist`, which
runs `scripts/run_sync.sh` every 3600 seconds. launchd also fires a
missed run right after the Mac wakes, which `cron` does not do.

One scheduled run is:

```bash
python -m scripts.sync_data --incremental \
    --snapshot-bucket day --retention-days 30
```

### Tuning without editing files

```bash
STORE_PULSE_RETENTION_DAYS=90 \
STORE_PULSE_SNAPSHOT_BUCKET=hour \
bash scripts/run_sync.sh
```

### Monitoring

```bash
tail -f logs/sync.log
launchctl print "gui/$(id -u)/com.storepulse.sync" | head -20
launchctl kickstart -k "gui/$(id -u)/com.storepulse.sync"   # force a run now
```

The fastest health check is not a log at all — it is the **Data** page's
three sync timestamps.

---

## Inspector scripts

`scripts/check_*.py` print what each layer sees, straight to the
terminal. They are the first tool to reach for when a dashboard number
looks wrong, because they bypass the API and the frontend entirely.

| Script | Checks |
| --- | --- |
| `check_connection.py` | Credentials and scopes |
| `check_products.py` | Product/variant collection |
| `check_inventory.py` | Inventory collection |
| `check_orders.py` | Order collection |
| `check_analytics.py` | ShopifyQL datasets |
| `check_database.py` | Stored tables and row counts |
| `check_metrics.py` | Computed daily metrics |
| `check_baseline.py` | Baseline values |
| `check_anomalies.py` | Anomaly verdicts |
| `check_forecast.py` | Forecast and backtest scores |
| `api_baseline.py` | API responses |

**Caveat:** these read the *live* database directly, not the serving
copy, so running one during a sync reports a lock error. That is not a
bug — wait for the run to finish.

---

## Tests

```bash
pytest -q
```

The suite covers pagination, database writes, each collector, metrics,
baselines, anomalies, forecasting, services, API formatting and
dependencies, the serving copy, the scheduler, and the analyst. The
read-only boundary has its own tests: the client must provide `query()`
only and must reject mutations before making a network request.

---

## Troubleshooting

### "Production DuckDB does not exist. Run scripts.sync_data first."

No database yet. Run `python -m scripts.sync_data`.

### `IO Error: Could not set lock on file "...duckdb"`

Something is writing while something else reads. Expected causes:

- A `check_*.py` script running during a sync — wait it out.
- Two syncs overlapping — the PID lock should prevent this; a second run
  exits with `[SKIP]`.
- A stale lock file after a crash: remove `data/*.duckdb.sync.lock`.

The API and the dashboards should never hit this, because they read the
published serving copy.

### The dashboard shows old data

Check, in order:

1. The **Data** page's three sync timestamps.
2. `tail logs/sync.log` for a failed run.
3. `launchctl print "gui/$(id -u)/com.storepulse.sync"` to confirm the
   agent is loaded.

Remember that **Refresh dashboard** only re-reads DuckDB. It cannot pull
newer data from Shopify.

### The Funnel page says "not available"

The ShopifyQL sessions snapshot has not been stored. Either the sync ran
with `--skip-analytics`, or the `read_reports` scope is missing. Confirm
with `python -m scripts.check_analytics`.

### Signals show CRITICAL every morning

Expected, and explained in [05 · Dashboard Guide](05-dashboard-guide.md):
a part-day is being scored against whole-day baselines. Check again once
the day is complete.

### The frontend shows an old UI after a code change

Run `npm --prefix frontend run build`. FastAPI serves `frontend/dist`,
not `frontend/src`.

### The Analyst page is disabled

`GEMINI_API_KEY` is not set. Everything else keeps working — the feature
degrades on its own by design.

---

## Database growth

At the default settings (`--snapshot-bucket day`, `--retention-days 30`)
the database stabilises around **0.16 GB**. Switching to an hourly bucket
takes it to roughly **3.9 GB** for the same retention.

Only switch to `hour` if you genuinely need hour-by-hour inventory
history. Nothing in `analytics/` uses it today: `metrics.py` reads only
the newest snapshot via `MAX(snapshot_at)`, and baseline and anomaly
detection work off orders.

---

Next: [09 · The AI Analyst](09-ai-analyst.md)
