# AI_USAGE.md

Updated as work happens, not reconstructed before submission — an entry
here the day work happened is worth more than a tidy summary written
after the fact.

---

### Entry 1 — Planning & full initial scaffold

**What:** Used Claude to work through the overall build strategy (scope
cuts, which sections carry the most rubric weight, tech stack choices),
then had it generate the entire initial codebase from that plan: the
FastAPI backend (all 4 endpoints + the 5th read-only metrics endpoint,
Pydantic schema, router heuristic, cost/estimator pure functions, tracer),
the pytest suite, the experiment/analysis scripts, and the React + tldraw
+ shadcn/ui frontend (custom draft shape, ROI capture, request lifecycle
hook, metrics panel, layout).

**What I verified myself, not just trusted:**
- Ran the backend test suite myself (`pytest`) — 32/32 passing
- Ran `tsc -b` and a real `vite build` on the frontend myself — both clean
- Cross-checked the tldraw v2.4.6 API against the actual installed
  package source (not just documentation) after the first draft used a
  newer-version API (`editor.toImage`) that doesn't exist in 2.4.x —
  caught by the build failing, fixed by reading `node_modules/tldraw/src`
  directly and switching to the real `exportToBlob` export
- Read through the router heuristic and adjusted the thresholds/text-
  detection logic myself — the initial version misclassified dense,
  high-density regions as "text-like"; a test I wrote against realistic
  inputs caught it

**What's still unverified / my own responsibility before this counts as
"my system":**
- The image-token tiling formula in `estimator.py` is a documented
  placeholder — I have not yet checked it against live Gemini docs (see
  the module's own docstring, which flags this)
- The rate table in `config/rates.yaml` has placeholder prices, not
  verified current pricing (see METRICS.md)
- Haven't yet run the app end-to-end against real Gemini/Ollama accounts
  — the SSE streaming path, the router's real-world threshold behavior,
  and the tldraw shape lifecycle are all validated by tests and type-
  checks, not by a live model call yet. That's day 1-2 work.

**Judgment calls I made, not the model:** which of the ~9 brainstormed
features to cut (IDEAS.md), the specific routing thresholds as a v1
starting point, and the overall scope cuts documented in README's
"Trade-offs & Scope Decisions."

---

### Entry 2 — Live testing, real bugs, and the schema rewrite against the actual brief

**What happened, roughly in order:** Got the app running live against
both Ollama and Gemini for the first time. This surfaced several real
bugs no amount of static review would have caught:

- A model's chain-of-thought leaking into visible drafts, via two
  *separate* mechanisms discovered in sequence — first a distinct
  `.reasoning` API field being read as if it were content (fixed by only
  reading `.content`), then, on a later real request, literal
  `<think>...</think>` tags showing up as plain text *inside* `.content`
  itself. Built a proper streaming-safe tag stripper (`think_filter.py`)
  for the second one, since a per-chunk regex can't handle a tag
  boundary split across two separate stream chunks — wrote it with tests
  covering exactly that split-boundary case before trusting it.
- Real Gemini traces showing `input_tokens + output_tokens ≠ total_tokens`
  — a ~198-token gap, later confirmed to be hidden reasoning tokens
  billed but not exposed anywhere in the OpenAI-compat usage object. This
  directly shaped the token schema rewrite below.
- The router's `ink_density` fast-tier threshold turned out to be
  mathematically unsatisfiable for any realistic drawing — caught by
  looking at one real trace's numbers, not by more code review.
- Model availability moving under us mid-build: `gemini-2.5-flash` got
  retired for new API keys between when it was chosen and when it was
  first actually called. Caught immediately by the API's own error
  message, not silently.

**Then: the actual assignment brief was shared for the first time in this
project's process.** Everything up to that point had been built against a
derived planning document (the PRD), not the source document. Diffing
against the real brief surfaced structural gaps that hadn't been visible
before — missing `ttfb`/`ttft` latency segments, 3 of 4 required KPIs
(CPAD/WTR/BC) not implemented, a token schema that didn't match the
brief's documented shape, no Markdown rendering (LaTeX-only), no
`ATTRIBUTION.md`. This is disclosed plainly rather than glossed over —
building against a close-but-not-identical derived spec for a stretch of
the project is a real gap in process, not just a list of missing features.

**Closing those gaps — what I verified myself, not just trusted:**
- Rewrote `models.py`, `cost.py`, `tracer.py`, `main.py` for the real
  trace schema and the brief's exact cost formula — ran the full test
  suite after (71 passing) and specifically re-verified the two token/KPI
  edge cases (zero denominators, reasoning-token billing) with hand-traced
  arithmetic, not just "tests pass."
- Built `kpis.py` (CPAD/DAR/WTR/BC) as pure functions with 17 tests
  covering every zero-denominator case *before* wiring it into the live
  endpoint — caught one real bug in my own test (a rounding-precision
  mismatch comparing a 4-decimal-rounded KPI output against an unrounded
  expected value) by actually running pytest and reading the failure, not
  by trusting the arithmetic on sight.
- Generated **synthetic trace data matching the exact new schema** and
  ran `analyze_traces.py` against it for real — confirmed it produces a
  real `REPORT.md`, real charts, real per-arm KPI numbers, not just that
  the script compiles.
- Added Markdown+LaTeX rendering via `react-markdown` + `remark-math` +
  `rehype-katex` (replacing an earlier LaTeX-only custom component,
  which was itself a real gap against the brief's explicit "at least
  Markdown and LaTeX" requirement). Broke the CSS file with a careless
  edit while adding supporting styles — a `str_replace` matched only the
  first two lines of a multi-line comment block, leaving the rest
  orphaned outside any `/* */` wrapper, which is exactly the kind of
  silent damage a `vite build` catches and a visual glance doesn't. Fixed
  and reran the real build to confirm, not just the type-checker.
- Verified **every tldraw API method** the new frame-timing stress-test
  script calls (`createShapes`, `setCamera`, `getCurrentPageShapeIds`,
  the `draw` shape's actual props schema) against the real installed
  source before shipping it — justified given this project had already
  been burned twice earlier by guessing at tldraw's API instead of
  checking. Also caught and fixed an early draft of that same script
  using invalid TypeScript syntax inside a plain `.js` console script,
  which would have thrown a syntax error the moment someone pasted it.

**What's still genuinely unverified / real work remaining, stated
plainly rather than implied as done:**
- `ATTRIBUTION.md` is a template, not filled in — it requires actually
  spending time with PenEcho (clone it, run it, read its docs/issues),
  which has not happened in this project's process yet. Fabricating
  plausible-sounding "borrowed ideas" from a repo neither of us has
  opened would be a worse integrity problem than the honest gap itself.
- The interaction frame-timing script is built and API-verified, but has
  not actually been run in a browser — the number in README is a
  placeholder pending that real run.
- The Five Canvases don't exist — this is real handwritten/sketched
  content that has to be produced by hand, not something that can be
  generated.
- The token estimator's MAE validation script is fixed and ready but has
  not been run against real Gemini calls (Gemini free-tier quota was
  exhausted mid-session — genuinely blocked by an external constraint,
  not skipped).
- No B5 experiment has been run for real yet; the harness works in
  synthetic mode but real benchmark-canvas data doesn't exist.

**Judgment calls made, not the model:** which structural gaps to
prioritize first given a hard ~48-hour deadline window discovered mid-session
(the KPI/schema rewrite over polish items like keyboard shortcuts, though
both got done); the decision to build ATTRIBUTION.md as an honest
template rather than either skip it or fabricate entries; the decision to
keep OpenRouter out of the graded B5 arms despite it offering a more
generous free-tier quota than Gemini, on measurement-integrity grounds.

---

_Next entry goes here — after a real B5 experiment run and the Five
Canvases exist._
