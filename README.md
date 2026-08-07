# Project SLATE

An infinite ink canvas (React + tldraw) where drawing or writing in a
region triggers an inline AI draft — completions, answers, corrections —
rendered directly on the canvas as a first-class object with its own
lifecycle (`pending → streaming → ready → accepted | discarded`).

Full design rationale lives in the PRD this repo was built from; this
README covers what actually shipped, how to run it, and the trade-offs
made along the way.

## Quickstart

**Backend**

```bash
cd backend
pip install -r requirements.txt --break-system-packages   # or use a venv
cp .env.example .env        # fill in GEMINI_API_KEY, or run Ollama locally
uvicorn main:app --reload --port 8000
```

Needs at least one real provider to actually generate drafts:
- **Gemini:** set `GEMINI_API_KEY` in `.env`
- **Ollama (local):** `ollama pull qwen3-vl:4b` and have Ollama running on `localhost:11434`

Verify it's up: `curl http://localhost:8000/health`

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env.local   # only needed if your backend isn't on :8000
npm run dev
```

Open the printed localhost URL. Draw something; a draft shape appears
after the idle timer (~1s) or immediately via the "Generate now" button.

**Tests**

```bash
# from repo root
pip install -r backend/requirements.txt --break-system-packages
pytest                       # 32 tests: cost, estimator/MAE, trace schema, router geometry
```

## Architecture

```
backend/
  main.py            4 lifecycle endpoints + 1 read-only metrics endpoint (see below)
  models.py           Pydantic schema — TraceLine, TokenUsage, LatencySegments, etc.
  router.py            the shipped feature: threshold-based model routing
  estimator.py          image token estimator + MAE validation
  cost.py                pure token+rate -> $ function
  tracer.py                buffers a trace per request_id, writes JSONL once complete
  adapters/client.py         one adapter, three provider configs (Gemini/Ollama/OpenRouter)
  config/rates.yaml            never-hard-coded pricing

frontend/src/
  components/canvas/    tldraw wrapper, custom DraftShapeUtil, ROI extraction, persistence
  components/panel/       live metrics panel (polls GET /metrics/summary)
  components/layout/       top bar (save/load/export, generate-now)
  hooks/useDraftLifecycle.ts   orchestrates capture -> request -> stream -> accept/discard
  lib/                          api client + types mirroring backend/models.py

scripts/
  analyze_traces.py    the only path from traces/*.jsonl to REPORT.md — see below
  run_experiment.py     B5 harness: pins provider per arm, interleaves requests
```

### Backend endpoint count

The backend surface is deliberately 4 endpoints for the request lifecycle
(`POST /requests`, `GET /requests/{id}/stream`, `DELETE /requests/{id}`,
`POST /requests/{id}/outcome`), matching the "minimal backend" scope
decision. A 5th, `GET /metrics/summary`, exists purely to feed the live
metrics panel with read-only aggregate stats — it does no writes, holds no
new state, and is a handful of lines. Called out explicitly here rather
than left for someone to notice the count doesn't match.

## Running the B5 experiment

```bash
# with real benchmark canvases:
python scripts/run_experiment.py --crops-dir benchmark_canvases/ --arms gemini,ollama --requests-per-arm 45

# or to exercise the harness before real canvases exist:
python scripts/run_experiment.py --synthetic 5 --arms gemini,ollama --requests-per-arm 10

python scripts/analyze_traces.py --traces backend/traces/traces.jsonl --out reports/
```

`scripts/analyze_traces.py` is the only code path that produces numbers
for `reports/REPORT.md` — every figure there traces back to this script,
not to hand-typing.

## Trade-offs & Scope Decisions

Everything below was a deliberate call, not something skipped for lack of
time. Stated here rather than left to be discovered.

**Canvas engine: tldraw, not a custom scene graph.**
Metrics + Experiment + the shipped feature carry more combined weight than
the canvas section. Rebuilding pan/zoom/undo/selection that a mature SDK
already solves correctly would have spent days on the lower-weighted
section for marginal gain — that time went into the metrics layer instead.

**No accounts, auth, or server-side persistence.**
Both are out of scope by design. Canvas save/load (`persistence.ts`) is a
pure client-side JSON blob operation — routing it through an API would add
a network hop and a persistence layer to solve a problem that doesn't
exist at single-user, local scale.

**No fine-tuning, no custom OCR/handwriting model.**
A modern multimodal model already reads handwriting; the system around it
— context extraction, routing, measurement — is what this project is
actually testing. Any DAR concerns get fixed by improving ROI extraction
(`components/canvas/roi.ts`), not by reaching for a fine-tune.

**SSE, not WebSockets.**
The request lifecycle needs one direction of continuous streaming (model
tokens) and one client-to-server signal (cancel). That's a GET stream
(`/requests/{id}/stream`) plus a DELETE endpoint — WebSockets would add
full duplex connection-state management for a channel direction that's
never actually used.

**No Docker, cloud deployment, or CI/CD.**
Out of scope. The bar is "clean clone to a working canvas in a few
commands, runs locally" — that's what the Quickstart above is built to hit.

**One shipped feature, not several.**
Model routing (`router.py`) was selected from 9 scored candidates in
`IDEAS.md` specifically because it's simultaneously a real (if small)
decision system, free to evaluate (reuses B2/B3's token/cost accounting
as its own scoring criteria), and directly reusable as the B5 experiment
variable — one build funds two sections.

**Backend surface kept to 4 (+1 read-only) endpoints.**
No services/repositories/controllers layering. That's architecture for a
team; this is a single-file, ~500-line backend where clean and readable
beats enterprise-shaped.

**OpenRouter used narrowly, kept out of the core experiment.**
Included in `adapters/client.py` for the router feature's cross-provider
access only. Excluded from B5's arms — it sits between the client and the
underlying model, so its latency/token numbers can't be independently
verified as reflecting the provider rather than the broker's own overhead.

## Known gaps as of this scaffold

Documented here rather than discovered later — see `AI_USAGE.md` for the
full verification log:

- Token estimator's tiling formula is an unverified placeholder — check
  against live provider docs before trusting `METRICS.md` numbers
- Rate table (`config/rates.yaml`) has placeholder prices
- Not yet run end-to-end against a live Gemini/Ollama account — tests and
  type-checks pass, but a real model call hasn't happened yet
- `benchmark_canvases/` (the Five Canvases) don't exist yet — day 1-2 work
