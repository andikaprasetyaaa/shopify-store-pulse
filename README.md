# Shopify Store Pulse - Milestone 1

Read-only Shopify Admin GraphQL foundation.

> **Looking for what the numbers mean rather than how to run this?**
> See [`docs/`](docs/README.md) - background, business process, data
> flow, a glossary, and a label-by-label guide to every page of the
> dashboard. This README stays focused on setup and commands.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with your shop slug and the custom app's client id and secret.
There is no access token to paste: `shopify/client.py` requests one at runtime
with a client credentials grant and refreshes it before it expires.
Never commit `.env`.

## Verify connection and scopes

```bash
python -m scripts.check_connection
```

Expected required scopes:

- `read_inventory`
- `read_locations`
- `read_orders`
- `read_products`
- `read_reports`

The check fails if a required scope is missing or any granted scope starts with
`write_`.

## The analyst (Gemini)

The Analyst page asks Gemini to *explain* the dashboard's figures. It is an
explainer, never a calculator: `services/analyst.py` assembles a snapshot from
the same services the dashboard renders from, and the system prompt in
`analyst/prompt.py` forbids the model from computing metrics, generating its own
forecast, or altering the supplied forecast values. Nothing raw from Shopify is
sent - only what the analytics layer already derived.

```bash
# .env  (NOT .env.example - that file is committed)
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash-lite
```

| Route | Purpose |
| --- | --- |
| `GET /api/analyst/status` | whether a key is configured; the page asks first so the rest of the dashboard works without one |
| `POST /api/analyst` | one question, answered over the current data |

Notes worth keeping:

- The API key travels in the `x-goog-api-key` **header**, never as a `?key=`
  query parameter, so it stays out of access logs and proxy traces. The query
  form also returns 404 for this model, while the header form works.
- Identical questions over identical data are served from a 5-minute in-memory
  cache, so pressing the button twice does not bill twice.
- `build_context` attaches an `anomaly_caveat` whenever the anomaly signals are
  dated today. `analytics/baseline.py` scores against the latest day present,
  which during trading hours is a part-day measured against a baseline of whole
  days - so every morning reads as a ~50% collapse. Without the caveat the
  analyst reported that mechanical artefact as its headline finding.
- The answer is untrusted text and is rendered with `textContent` only; the
  page never puts model output through `innerHTML`.
- The whole feature degrades to a message when `GEMINI_API_KEY` is absent. The
  dashboard does not depend on it.

## Dashboard design

The frontend has one design decision worth writing down: the chart colours are
not free choices.

`frontend/src/styles.css` defines the palette as CSS custom properties in three
blocks - light on `:root`, dark under `prefers-color-scheme`, and dark again
under `[data-theme="dark"]` so the in-app switch wins in both directions. The
Appearance control in the sidebar is three-state (Light / Dark / Auto); Auto is
the default and stores nothing, so a reader who never touches it follows their
OS.

The data colours came from a validator rather than from taste:

| Role | Light | Dark |
| --- | --- | --- |
| Series 1 (revenue, orders, actuals) | `#2a78d6` | `#3987e5` |
| Series 2 (baseline, forecast, band) | `#eb6834` | `#d95926` |
| Funnel stages | four steps of one blue ramp | same ramp, re-stepped |

Both modes clear the colourblind-separation, chroma, lightness-band and contrast
gates. Re-run the check before changing any of these values.

Charts read these tokens with `getComputedStyle` at draw time, which is why
`charts.ts` redraws on a theme change instead of relying on CSS alone: an SVG
`stroke` attribute is already a resolved colour by the time the theme flips.

Every chart ships a hover crosshair with a tooltip, keyboard support (focus the
plot, then arrow keys), and a **Table** toggle. The table is not optional
decoration - it is what keeps every value readable without a pointer.

## Run it

Two ways to run, depending on whether you are editing the frontend.

### Normal use: one process

The API serves the built frontend, so a single process is the whole app.

```bash
source .venv/bin/activate
npm --prefix frontend run build   # only after changing frontend/src
uvicorn api.app:app --port 8000
```

Open <http://127.0.0.1:8000>. The OpenAPI docs are at `/docs`.

### Editing the frontend: two processes

Vite serves the TypeScript directly with hot reload and proxies `/api` to the
API, so both halves read the same DuckDB file.

```bash
# terminal 1
source .venv/bin/activate
uvicorn api.app:app --reload --port 8000

# terminal 2
npm --prefix frontend run dev
```

Open <http://localhost:5173>. Port 8000 must be the API's, since that is what
`vite.config.ts` proxies to; :8000 still serves the last *built* bundle, which
is not what you are editing.

The Streamlit dashboard is separate from all of this and still runs on its own:

```bash
streamlit run dashboard/app.py
```

Nothing here calls Shopify. Every process reads `data/serving.duckdb`, which
`scripts/sync_data.py` publishes.

## Build the dashboard frontend

`frontend/` is a TypeScript app built by Vite. The API serves the build output,
so it has to be built once before `/` will load:

```bash
cd frontend
npm install
npm run build
```

| Command | What it does |
| --- | --- |
| `npm run build` | type-checks, then writes `frontend/dist` (what FastAPI serves) |
| `npm run typecheck` | `tsc --noEmit` only, for CI or a quick check |
| `npm run dev` | Vite dev server on :5173 with hot reload, proxying `/api` to :8000 |

`npm run dev` expects `uvicorn api.app:app` to already be running on port 8000;
it proxies every `/api` call there so the dev server reads the same DuckDB data
as production.

`frontend/dist` and `frontend/node_modules` are not committed. After pulling a
change to `frontend/src`, re-run `npm run build` or the browser keeps the old
bundle.

## Test read-only boundary

```bash
pytest -q
```

The client intentionally provides `query()` only and rejects GraphQL mutations
before making a network request.


## Automatic hourly sync

`scripts/sync_data.py` is safe to re-run: every current-state table has a
primary key and is written with `INSERT OR REPLACE`, so re-fetched rows
overwrite the old version instead of duplicating.

| Table | Key | Repeat run |
| --- | --- | --- |
| `products`, `product_variants` | product / variant id | overwritten |
| `inventory_items` | inventory item id | overwritten |
| `orders`, `order_line_items` | order / line item id | overwritten |
| `inventory_snapshots` | `(snapshot_at, inventory_level_id)` | overwritten inside the same bucket |
| `analytics_snapshots(_rows)` | `(dataset_name, snapshot_at, ...)` | overwritten inside the same bucket |

Snapshot timestamps are rounded down by `--snapshot-bucket` (default `day`),
so every run inside the same bucket replaces the previous one instead of
piling up another copy of ~72k inventory rows. Snapshot rows for a bucket are
deleted before the rewrite, so a shrinking catalog leaves no stale rows behind.

Bucketing does not reduce freshness. The job still runs hourly and still
overwrites with current data every hour; the bucket only controls how much
*history* is retained. One measured inventory snapshot is 72,260 rows and
5.5 MB, which is why the default is `day`:

| `--snapshot-bucket` | Retained per day | Database at 30-day retention |
| --- | --- | --- |
| `day` (default) | 1 snapshot, 5.5 MB | ~0.16 GB |
| `hour` | 24 snapshots, 0.13 GB | ~3.9 GB |

Use `hour` only if you genuinely need hour-by-hour inventory history. Nothing
in `analytics/` requires it today: `metrics.py` reads only the newest snapshot
via `MAX(snapshot_at)`, and baseline/anomaly detection works off orders.

### Install the schedule (macOS launchd)

`scripts/com.storepulse.sync.plist` is **not committed**: it holds
absolute paths for the machine it was installed on, which are neither
portable nor anyone else's business. Create it once from this template,
replacing both occurrences of `PROJECT_DIR` with the absolute path to
your checkout:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.storepulse.sync</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>PROJECT_DIR/scripts/run_sync.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>PROJECT_DIR</string>

    <!-- Every 3600 seconds. launchd also fires this
         as soon as the Mac wakes if an hour elapsed
         while it was asleep. -->
    <key>StartInterval</key>
    <integer>3600</integer>

    <!-- Run once right after loading, so the first
         sync does not wait a full hour. -->
    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>PROJECT_DIR/logs/launchd.out.log</string>

    <key>StandardErrorPath</key>
    <string>PROJECT_DIR/logs/launchd.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

Then:

```bash
bash scripts/install_schedule.sh          # install + run once now
bash scripts/install_schedule.sh remove   # uninstall
```

This installs `~/Library/LaunchAgents/com.storepulse.sync.plist`, which runs
`scripts/run_sync.sh` every 3600 seconds. launchd also fires a missed run right
after the Mac wakes, which `cron` does not do.

### What one scheduled run does

```bash
scripts/run_sync.sh
# -> python -m scripts.sync_data --incremental \
#      --snapshot-bucket day --retention-days 30
```

- `--incremental` refetches only orders with
  `updated_at:>= <newest stored update - overlap>` (`--overlap-minutes`,
  default 90) instead of all 5k+ orders every hour. Changed orders overwrite
  their existing rows by primary key.
- Products and inventory are always fetched in full; Shopify has no
  incremental filter for them.
- `--retention-days 30` deletes snapshot rows older than 30 days after a
  successful run, then checkpoints the database. Use `0` to keep everything.
- A PID lock (`data/*.duckdb.sync.lock`) makes an overlapping run exit with
  `[SKIP]` rather than collide on DuckDB's single-writer lock.
- The runner retries up to 3 times, 60s apart, which covers the brief moments
  the FastAPI/Streamlit read-only connections hold the database file.

### Tuning without editing files

```bash
STORE_PULSE_RETENTION_DAYS=90 \
STORE_PULSE_SNAPSHOT_BUCKET=hour \
bash scripts/run_sync.sh
```

### Watch it

```bash
tail -f logs/sync.log
launchctl print "gui/$(id -u)/com.storepulse.sync" | head -20
launchctl kickstart -k "gui/$(id -u)/com.storepulse.sync"   # force a run now
```


## Why there are two database files

DuckDB is embedded, not a server. It allows **one** writer or **many** readers,
never both at once. An hourly sync holds the write lock for the whole run, so a
dashboard reading the same file would fail for minutes at a time with:

```
IO Error: Could not set lock on file "...duckdb": Conflicting lock is held ...
```

So the sync writes to one file and publishes a copy for readers:

| File | Written by | Read by |
| --- | --- | --- |
| `data/shopify_store_pulse.duckdb` | `scripts/sync_data.py` only | nothing |
| `data/serving.duckdb` | published at the end of each run | `api/app.py`, `dashboard/app.py` |

At the end of a successful sync — after the write connection is checkpointed
and closed — `publish_serving_copy()` copies the database to
`data/serving.duckdb.tmp` and renames it into place. The rename is atomic on
the same filesystem, so a reader sees either the previous copy or the new one,
never a half-written file. Readers that already hold the old file keep reading
it safely until they close it.

`resolve_read_path()` picks the serving copy when it exists and falls back to
the live database otherwise, so a fresh checkout works before the first sync.
`api/app.py` re-resolves on every request, so a copy published after the API
started is picked up without a restart.

Use `--no-publish` to skip the copy. Note that `scripts/check_*.py` still read
the live database directly and will report a lock error if run during a sync.
