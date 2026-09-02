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

### Two answer shapes

The prompt asks the model to match its answer to the question. A
substantial analytical question — or the opening question of a
conversation — gets the full structured report below. A short follow-up
inside an ongoing conversation (*"why?"*, *"is that bad?"*, *"which
product?"*) gets a direct answer of a sentence or a short paragraph, with
no headings and no restatement of the analysis.

Only the length adapts. Every prohibition above still applies to a
follow-up, and claims are still labelled OBSERVED / FORECAST /
INFERENCE.

`services/analyst.py` reinforces this next to the data: when the request
carries a conversation, `build_user_prompt(..., follow_up=True)` swaps
the six-heading instruction for one asking for a direct answer.

### The six sections

The structured report follows this order, and a test asserts that the
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

## The conversation

The feature is multi-turn, and the design has one unusual property worth
stating plainly: **the server keeps no session.** The browser holds the
transcript and posts it back with every question.

| Concern | How it is handled |
| --- | --- |
| **Where it lives** | `state.analystChat` in the frontend. Leaving for another page and returning keeps the thread; reloading starts a new one. |
| **How it reaches Gemini** | `GeminiClient.generate(history=...)` sends earlier turns as `contents` ahead of the question. |
| **Which turns are sent** | Completed ones only. A pending placeholder or a failed turn is never sent back — it would teach the model that an error was part of the conversation. |
| **How much is sent** | The last 20 turns (`MAX_HISTORY_TURNS`). The route caps a request at 40 messages of 20,000 characters each. |
| **Where the data goes** | On the current turn only. Earlier turns carry their text alone. |
| **Trust** | The transcript arrives from the browser, so it is treated as input: `normalize_history()` drops unknown roles, non-string text and empty messages, and the route rejects an unknown role with a 422. |

### Why the data is not repeated on every turn

Attaching the full context JSON to each turn would make a conversation
cost more with every question, and would hand the model several
increasingly stale copies of the same figures to choose between. Sending
it once, on the live question, keeps the cost flat and leaves exactly one
set of numbers the model may cite — which is the whole premise of the
feature.

The trade-off: the model's memory of earlier turns is its own prose, not
the data those answers were computed from. That is the correct
arrangement here, since it is forbidden from recomputing anything
anyway.

## Engineering details

### API key handling

The key travels in the `x-goog-api-key` **header**, never as a `?key=`
query parameter. Two reasons: it stays out of access logs and proxy
traces, and the query form returns 404 for this model anyway while the
header form works.

### Caching

Identical questions over identical data **in the same conversation** are
served from a 5-minute in-memory cache (`CACHE_TTL_SECONDS = 300`), keyed
by a hash of the question, the context and the history. Asking the same
thing twice does not bill twice. Cached answers are labelled **cached**
under the reply.

History is part of the key on purpose: *"why?"* after the revenue answer
and *"why?"* after the stock answer are not the same question, and must
not share a cached reply.

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
