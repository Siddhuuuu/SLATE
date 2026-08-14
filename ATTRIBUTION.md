# ATTRIBUTION.md

## ⚠️ Status: template only — requires real review of PenEcho before submission

Per the brief (Section 2): "If you deliberately reimplement a specific
idea from [PenEcho], say so in ATTRIBUTION.md — one line per borrowed
idea. Honest attribution earns marks. Silent copying loses all of them."

That instruction assumes you've actually done the prep work the brief
also asks for: "Run it first. Spend an evening actually using it... Read
the architecture notes... Read its open issues and discussions." **That
hasn't happened yet in this project's process** — SLATE's design came
from first-principles planning (the PRD), not from studying PenEcho's
actual implementation.

Two honest paths from here, your call:

1. **Actually spend 30-60 minutes with PenEcho** (github.com/penecho/penecho)
   before the deadline — clone it, run it, skim `docs/architecture.md` and
   a few open issues. Then fill in the table below with anything genuinely
   borrowed (the brief's own example — "a returned answer should be a
   movable draft you accept or discard" — is a real, fair example of the
   *kind* of thing that belongs here: an idea, not implementation code).

2. **If you genuinely didn't study it**, say that plainly instead of
   inventing entries. An honest "I did not study PenEcho's implementation
   in detail; SLATE's design was developed independently from the brief's
   own requirements" is a true, defensible statement. Fabricated
   attribution to a project you didn't actually examine is arguably worse
   than an honest gap — it's inventing review evidence, which is exactly
   the kind of thing "Integrity & attribution" is scored on.

## Ideas borrowed from PenEcho (fill in after actually reviewing it)

| PenEcho idea | Where it shows up in SLATE | Why borrowed |
|---|---|---|
| _e.g. "answers are movable drafts, not chat messages"_ | _e.g. DraftShapeUtil.tsx's accept/discard state machine_ | _e.g. matches this project's own A4 requirement directly_ |

## Explicitly NOT borrowed — implemented independently

Worth stating plainly, not just leaving blank, since it shows deliberate
divergence rather than accidental non-overlap:

- The metrics/KPI layer (`backend/kpis.py`, the six-segment latency model)
  was built directly from this assignment's own Section 5 spec, not from
  PenEcho's architecture.
- The router/tiered-model feature (`backend/router.py`) was one of 9
  scored candidates in `IDEAS.md`, selected independently.

## Other references consulted

- tldraw's own documentation and source (`node_modules/tldraw/src` was
  read directly during development to confirm the real `ShapeUtil` API
  and `exportToBlob` signature — see `AI_USAGE.md` for that debugging
  story) — this is normal library usage, not something requiring
  attribution under the brief's PenEcho-specific rule, but noted here for
  completeness.
- W3C Pointer Events spec — referenced for coalesced-event handling
  guidance (confirm in README whether this was actually implemented, or
  note it as a known gap).
