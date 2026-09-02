# 09 · The AI Analyst

## What it is

A Gemini-backed feature that **explains** the dashboard's figures in
prose. One idea holds the whole design together:

> **The model is an explainer, never a calculator.**

Every number it is allowed to cite has already been computed by the same
services the dashboard renders from. It therefore cannot disagree with
the screen — not because it is well-behaved, but because it was never
given the means to produce a different number.

---

## What it receives

`services/analyst.py` → `build_context()` assembles a compact, factual
snapshot:

| Block | Source | Content |
| --- | --- | --- |
| Overview | `build_overview(days)` | KPIs, period comparison, trend |
| Signals | `build_signals()` | Anomaly verdicts and their severities |
| Forecast | `build_forecast(metric, horizon)` | Predictions, bands, backtest accuracy |
| Inventory | `build_inventory(threshold, "", RISK_SAMPLE)` | Stock summary plus **15** low-stock rows |
| Metadata | `database_metadata()` | Freshness and coverage |

Two constraints worth naming:

- **Nothing raw from Shopify is sent.** Only what the analytics layer has
  already derived.
- **Only 15 low-stock rows travel with the context** (`RISK_SAMPLE`). The
  model needs a sense of the risk, not the whole table — and 70k variants
  would not fit anyway.

Each block is explicitly labelled with what it is, because the prompt
asks the model to keep OBSERVED separate from FORECAST, and it can only
do that if the input says which is which.

---

## The behavioural contract

`analyst/prompt.py` holds the system prompt verbatim and in one place. It
is the entire contract for the feature. The prohibitions:

- Does **not** calculate business metrics from raw Shopify data.
- Does **not** generate forecasts itself.
- Does **not** invent numbers.
- Does **not** assume causes unsupported by evidence.
- Does **not** perform any Shopify write operation.

All quantitative claims must come from the supplied data.

### Forecast-specific rules

Because the store has only ~60 days of history, the prompt instructs the
model to:

- Treat forecasts as short-term estimates.
- Not claim yearly or long-term seasonality.
- Not claim high confidence unless the supplied evaluation supports it.
- Prefer 7-day forecasts over long projections.
- Never modify the supplied forecast values.

### The six sections

Every answer follows this structure, and a test asserts that the
frontend's headings still match the prompt text:

| # | Section | Purpose |
| --- | --- | --- |
| 1 | **Summary** | The single most important finding |
| 2 | **Evidence** | The metrics supporting it |
| 3 | **Likely explanation** | The most plausible interpretation, hedged where causality is unproven |
| 4 | **Forecast** | The supplied forecast and its uncertainty |
| 5 | **Priority** | What deserves attention first |
| 6 | **Recommended investigation** | What to inspect next — analytical only |

### The three epistemic labels

| Label | Meaning | How to treat it |
| --- | --- | --- |
| **OBSERVED** | Calculated directly from Shopify data | Fact |
| **FORECAST** | Produced by the forecasting model | Estimate, with a band |
| **INFERENCE** | The model's interpretation | Hypothesis — verify before acting |

The prompt forbids presenting an inference as an observed fact. When
evidence is insufficient, the model is instructed to say so verbatim:
*"There is not enough evidence in the available data to determine the
cause."*

---

## The anomaly caveat

`build_context()` attaches an `anomaly_caveat` whenever the anomaly
signals are dated today.

The reason is concrete. `analytics/baseline.py` scores against the latest
day present, which during trading hours is a part-day measured against a
baseline of whole days — so every morning reads as a ~50% collapse.
Without the caveat, the analyst reported that mechanical artefact as its
headline finding.

This is a good illustration of the general pattern: the model is only as
honest as its context, so the context carries the warnings the numbers
alone cannot.

---

## Engineering details

### API key handling

The key travels in the `x-goog-api-key` **header**, never as a `?key=`
query parameter. Two reasons: it stays out of access logs and proxy
traces, and the query form returns 404 for this model anyway while the
header form works.

### Caching

Identical questions over identical data are served from a 5-minute
in-memory cache (`CACHE_TTL_SECONDS = 300`), keyed by a hash of the
question and the context. Pressing the button twice does not bill twice.
Cached answers are labelled **· cached** in the UI.

### Output safety

The answer is untrusted text. It is rendered with `textContent` only; the
page never puts model output through `innerHTML`.

### Graceful degradation

The whole feature reduces to a message when `GEMINI_API_KEY` is absent.
The frontend calls `GET /api/analyst/status` before rendering, precisely
so the rest of the dashboard works without a key. Nothing else depends on
it.

### Routes

| Route | Purpose |
| --- | --- |
| `GET /api/analyst/status` | Whether a key is configured |
| `POST /api/analyst` | One question, answered over the current data |

### Configuration

```bash
# .env  (NOT .env.example - that file is committed)
GEMINI_API_KEY=...
GEMINI_MODEL=...
```

`GEMINI_MODEL` is deliberately not pinned in this document: the committed
`.env.example` and the live `.env` currently name different models, and
the value is expected to move as newer models ship. Read the actual value
from `.env`, or from the model name the Analyst page prints under its
answer.

---

## Using it well

### The preset questions

| Preset | Sent question |
| --- | --- |
| **Explain current state** | "Explain the store's current state using the supplied data." |
| **Biggest risk** | "What is the single biggest risk visible in this data, and how confident can we be about it?" |
| **Read the forecast** | "Explain the forecast and how much trust the backtest justifies." |
| **Inventory exposure** | "What does the inventory data say about stock risk?" |

### Questions that work

- "Why did orders fall yesterday?"
- "Which funnel stage is the weakest right now?"
- "Should I trust this week's forecast?"
- "Which products are most at risk of stocking out?"

### Questions that will not work

- **"What was revenue in January?"** — outside the 60-day window; the
  data is not there.
- **"Compare this to last year."** — no year-over-year data exists.
- **"Recalculate AOV excluding shipping."** — the model is not allowed to
  compute metrics, and shipping is not in the context.
- **"Update the price of this product."** — read-only, at every layer.

### The reporting window matters

The Analyst page shares the Overview's **Reporting window** control,
because that window decides what is sent to the model. Ask the same
question over 7 days and over 60 days and you will get different answers
— correctly so.

---

Back to the [index](README.md).
