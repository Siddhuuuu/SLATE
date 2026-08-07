# IDEAS.md — Feature ideation (Part C1)

Scored on **impact** (does it change how the tool is actually used, not just
demo well), **effort** (days, given the infra already built for Part B),
and **running cost** (ongoing $ or complexity it adds after ship). Rubric
explicitly rewards one feature at ~95% over three at ~60%, so the point of
this list is the *elimination*, not just the winner.

| # | Idea | Impact | Effort | Cost | model_dependency | risk | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **Model routing (cheap/local vs. heavy/cloud) by region complexity** | High — real product decision, not a demo trick; every request goes through it | Low — reuses the adapter + tracer infra from Part B entirely | ~free — a threshold function, no new dependency | Router logic only, not the underlying VLM | Thresholds are a v1 guess, unvalidated until real trace data exists | **Selected — see §10 of the PRD, built as `backend/router.py`** |
| 2 | Multi-region "batch" capture (send several ink clusters in one request) | Medium — saves round-trips on dense pages | Medium — needs region-merge logic + a different prompt shape | Low | High — depends on model handling multi-region prompts well | Harder to keep the trace schema at "one line per request" | Cut — complicates B's "one line per request" invariant for a marginal UX win |
| 3 | Persistent conversation memory across drafts (drafts reference earlier accepted ones) | Medium | Medium-high — needs a memory/context store beyond "nearby accepted drafts" | Low | High | Scope creep toward a stateful backend the brief explicitly discourages | Cut — partially already covered by `nearby_accepted_draft_ids` in A3, the rest isn't worth a stateful backend |
| 4 | Voice-triggered capture ("say 'draft this'" instead of idle timer) | Low-medium — novelty, unclear it's actually faster than idle/gesture | Medium — new input modality, browser speech API quirks | Low | None | Accessibility win is real but orthogonal to what's scored | Cut — doesn't touch Metrics/Experiment/routing, low ROI per the PRD's own framing |
| 5 | Confidence-scored drafts (model self-rates certainty, shown as a badge) | Medium | Medium — needs a second model call or a parsed confidence token | Doubles cost per request if it's a second call | High — confidence self-reports are notoriously unreliable | Could actively mislead users if the self-rating is bad | Cut — the honest-failure requirement (A6) is better served by just showing errors plainly |
| 6 | Client-side offline mode (cache last N drafts, work without backend) | Low | Medium | Low | None | None | Cut — single-user local tool already starts fast; offline mode solves a problem nobody has here |
| 7 | Handwriting-style transfer (drafts rendered in the user's own ink style) | Low — cute, not useful | High — a genuinely hard generation problem | Unknown, possibly high (another model call) | Very high | Directly adjacent to "fine-tuning temptation" the brief warns against | Cut — this is the DAR-is-weak trap from the risk register; fix context extraction, not add a gimmick |
| 8 | Cost-budget guardrail (pause auto-generation after $X/session) | Medium — genuinely useful safety net | Low — pure function over the same cost.py output | ~free | None | Low | Cut for v1, noted as a natural follow-up once B's cost accounting is validated — see METRICS.md |
| 9 | Shareable read-only canvas link | Low for this brief's scoring — implies a backend + hosting the PRD explicitly rules out | High — needs persistence, auth-lite, hosting | Ongoing hosting cost | None | Directly violates the "no accounts, no server-side persistence" scope decision | Cut — see README "Trade-offs & Scope Decisions" |

## Why #1 won

Model routing is the only idea on this list that is simultaneously:
- A genuine (if small) decision system — a real classification/policy problem, not UI sugar
- Free to evaluate — it reuses B2/B3's token counts, cost, and outcome data as its own scoring criteria, nothing new to instrument
- Directly reusable as the B5 experiment variable, so one build funds two rubric sections

Full spec: PRD §10. Implementation: `backend/router.py`. Thresholds and
their reasoning: see the docstring and `RoutingThresholds` dataclass in
that file — revisit them once `scripts/analyze_traces.py` has real data
to tune against.
