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

_Next entry goes here — after day 1-2 handwriting-sample testing and the
first real end-to-end model call._
