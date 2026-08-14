# IDEAS.md — Feature ideation (Section 6, C1)

9 ideas, each scored on the brief's exact template — `problem` (the
specific user moment, not a capability), `why_canvas` (why this is better
spatial than in a chat window — if it isn't, the idea gets cut right
there), `model_dependency`, `cost_class`, `risk`. Selection argument and
scoring table follow.

---

### 1. Model routing by region complexity — SELECTED, see C2

**problem:** Every request currently pays cloud latency/cost even for a
trivial region (a single digit, a short word) that a small local model
handles fine — the user waits and pays the same either way regardless of
how simple the ink actually is.
**why_canvas:** The router's input signals (stroke count, ink density,
bounding-box size) only exist because the canvas gives spatial structure
to reason about — a chat window has no equivalent "how complex is this
region" signal to route on.
**model_dependency:** Router logic only — works with any vision model on
either tier, no dependency on a specific model's capabilities.
**cost_class:** cheap — a threshold function, no new API calls, reuses
existing token/cost infra entirely.
**risk:** Thresholds are a v1 heuristic guess, unvalidated until real
trace data exists to tune against (see `router.py`'s own docstring).

---

### 2. Multi-region "batch" capture

**problem:** A dense page with several separate ink clusters currently
fires one request per cluster — each waits and costs independently even
though a person often finishes several small regions in one sitting.
**why_canvas:** Batching only makes sense because the canvas already
knows the spatial location of each cluster; a chat window has no
equivalent notion of "several separate regions in one view."
**model_dependency:** High — depends on the model reliably handling a
multi-region prompt and returning per-region answers, not one merged one.
**cost_class:** moderate — fewer round-trips, but a bigger single prompt.
**risk:** Complicates the trace schema's "one line per request" invariant
— a batch either needs N trace lines from one API call (messy) or loses
per-region latency/cost granularity.

---

### 3. Persistent memory across drafts

**problem:** A draft has no memory of earlier accepted work elsewhere on
the canvas beyond the "nearby accepted drafts" already sent as context —
a follow-up answer can contradict something decided minutes earlier.
**why_canvas:** The canvas is the natural place to store this — spatial
proximity already implies relatedness, unlike a flat chat history.
**model_dependency:** High — needs the model to actually use extended
context well, not just receive it.
**cost_class:** moderate-high — growing context on every request.
**risk:** Scope creep toward a stateful backend the brief explicitly
discourages; partially already covered by A3's `nearby_accepted_draft_ids`.

---

### 4. Voice-triggered capture

**problem:** Reaching for "Generate now" or waiting on the idle timer
breaks flow for someone whose hands are already full holding a stylus.
**why_canvas:** Weak fit — voice triggering a canvas action isn't
meaningfully more spatial than voice triggering anything else; the
canvas isn't doing the work here.
**model_dependency:** None for the trigger itself; a speech API only.
**cost_class:** cheap.
**risk:** Real accessibility win, but doesn't touch Metrics, Experiment,
or the shipped-feature story — low ROI against what's actually scored.

---

### 5. Confidence-scored drafts

**problem:** A user can't tell, before reading closely, whether a draft
is a confident answer or a shaky guess.
**why_canvas:** Neutral — a confidence badge works identically in a chat
bubble; nothing about the canvas makes this better.
**model_dependency:** High — self-reported confidence from LLMs is
notoriously unreliable; would need a second call or a fragile parsed token.
**cost_class:** expensive if a second call; moderate if parsed from one.
**risk:** Could actively mislead if the self-rating is wrong — the
honest-failure requirement is better served by just showing real errors
plainly than by a badge that might lie.

---

### 6. Client-side offline mode

**problem:** No response if the backend is briefly unreachable.
**why_canvas:** Neutral — offline caching isn't a spatial-canvas idea,
it's a general web-app resilience pattern.
**model_dependency:** None.
**cost_class:** cheap.
**risk:** Low risk, but also low payoff — a single-user local tool
already starts in seconds; this solves a problem that mostly doesn't
exist here.

---

### 7. Handwriting-style transfer

**problem:** Drafts render in a generic font, visually distinct from the
user's own ink — some users might want drafts styled to blend in.
**why_canvas:** Strong fit conceptually (it's specifically about how
canvas objects look next to ink), but it's a generation problem, not a
canvas one.
**model_dependency:** Very high — a genuinely hard generative task.
**cost_class:** high — likely a second, more expensive model call.
**risk:** Directly adjacent to the fine-tuning temptation the brief warns
against; if draft quality (DAR) looks weak, the real fix is better context
extraction, not a styling gimmick.

---

### 8. Cost-budget guardrail

**problem:** Nothing stops a session from quietly running up cost if
someone keeps triggering heavy-tier requests.
**why_canvas:** Neutral — a budget cap is a backend policy, not
specifically a canvas idea.
**model_dependency:** None.
**cost_class:** cheap — a pure function over `cost.py`'s existing output.
**risk:** Low. Genuinely useful; the actual reason it wasn't chosen is
that it doesn't showcase anything new about *this* project specifically
— see quota_guard.py, which ended up shipping a version of exactly this
for Gemini specifically, just not as the headline feature.

---

### 9. Shareable read-only canvas link

**problem:** No way to send a finished canvas to someone without them
also having the app running locally.
**why_canvas:** Strong fit in principle — sharing spatial work is a real
canvas-native need.
**model_dependency:** None.
**cost_class:** high ongoing — needs persistence, hosting, some amount of
auth-lite.
**risk:** Directly violates the brief's explicit out-of-scope list (no
accounts, no cloud deployment) — this one isn't a judgment call, it's
ruled out by name.

---

## Scoring & selection

| # | Idea | Impact | Effort | Running cost | Verdict |
|---|---|---|---|---|---|
| 1 | Model routing | High | Low (reuses B's infra) | ~free | **Selected** |
| 2 | Multi-region batch | Medium | Medium | Low | Cut |
| 3 | Persistent memory | Medium | Medium-high | Low | Cut |
| 4 | Voice trigger | Low-medium | Medium | Low | Cut |
| 5 | Confidence scores | Medium | Medium | Doubles cost if 2nd call | Cut |
| 6 | Offline mode | Low | Medium | Low | Cut |
| 7 | Handwriting-style transfer | Low | High | High | Cut |
| 8 | Cost guardrail | Medium | Low | ~free | Cut (partially shipped anyway, see quota_guard.py) |
| 9 | Shareable link | Low (for this brief) | High | Ongoing hosting | Cut — explicitly out of scope |

**Why #1 won, and what I most wanted to build instead:** Model routing is
the only idea that is simultaneously a genuine (if small) decision
system, free to evaluate (it reuses the token/cost/outcome data the
metrics layer already produces as its own scoring criteria), and directly
reusable as the B5 experiment variable — one build funds two scored
sections. The idea I most wanted to build was **#9, the shareable
canvas link** — it's the one with the clearest "why_canvas" story of the
cut ideas, spatial work genuinely wants to be shared spatially. It lost
specifically because the brief rules out exactly the infrastructure it
would need (accounts, hosting), not because the idea itself is weak.

Full implementation: `backend/router.py`. Thresholds and reasoning: see
that file's docstring and `RoutingThresholds` dataclass — revisit once
`scripts/analyze_traces.py` has real data to tune against.
