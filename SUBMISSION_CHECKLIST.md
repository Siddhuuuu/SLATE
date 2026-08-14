# SLATE — Submission Checklist (triaged against ~48h remaining)

**Deadline: 14 Aug 2026, 23:59 IST. Today: 12 Aug.** Everything below is
ordered by (deliverable-gate risk) × (point value) ÷ (time to fix), not by
when it was found or how satisfying it is to fix.

Deliverables are **all-or-nothing per item** — "a missing one is a zero for
its criterion, not a deduction." That structural fact drives most of the
prioritization below: a half-finished REPORT.md and a missing REPORT.md
score the same (zero), so partial progress on a missing deliverable is
worth more than polish on one that already exists.

---

## Part 0 — What's genuinely solid (real credit, not just gap-hunting)

- End-to-end loop works **live**, against both Gemini and Ollama, not just in tests
- Several real bugs found and fixed through actual usage, not guesswork: two independent reasoning-leak mechanisms (separate `.reasoning` field, then literal `<think>` tags in content), an ink-accumulation math bug, a cost-accounting gap (198 hidden tokens), an `ink_density` threshold that was mathematically unsatisfiable
- Quota protection built and tested against your real free-tier numbers
- 49 passing tests across cost, estimator, schema, router, quota guard, think-filter
- `AI_USAGE.md` has been genuinely continuous and specific, not reconstructed after the fact — this is a real strength, keep doing it
- README's trade-offs section reflects real decisions, not invented ones

This is more done than a typical submission at this stage. The gaps below are real, but they're gaps in an otherwise-working system, not signs of a system that doesn't work.

---

## Part 1 — The 8 hard deliverable gates

Check each honestly. ⬜ = at real risk of scoring zero for that criterion.

- [ ] **1. Repository** — public? Tagged `git tag submission` before you send the email? (Untagged = later commits could be reviewed instead of what you intended.)
- [ ] **2. README.md** — has: setup ≤3 commands ✅ · architecture **diagram** (a real diagram, not prose — currently missing) · declared latency budget (e.g. "p95 e2e ≤ 8s" — **not stated anywhere yet, and BC/Budget Compliance KPI is meaningless without it**) · measured frame timing at 5,000+ strokes (**not done**) · known limitations ✅ (needs updating with everything below)
- [ ] **3. METRICS.md** — trace schema (⚠️ doesn't match the required schema, see Part 2) · segment definitions (⚠️ only 4 of 6 required segments exist) · estimator MAE (⏳ pending tomorrow's validation run — **must happen**) · rate table + source/date (⚠️ still an unverified placeholder, flagged twice already) · panel screenshot (missing)
- [ ] **4. REPORT.md** — **does not exist.** Needs the Five Canvases, a real experiment run, p50/p95 tables, a chart, two before/after optimizations. This is the single biggest gap on this list.
- [ ] **5. IDEAS.md** — exists, 9 ideas ✅, but check the exact required fields: `problem / why_canvas / model_dependency / cost_class / risk`. Current version doesn't use `why_canvas` explicitly — that's a named assessment axis, not a nice-to-have. Cheap to add, don't skip it.
- [ ] **6. traces/** — needs ≥50 real, redacted trace lines + the five benchmark canvas files as committed JSON. Neither exists yet at the required volume.
- [ ] **7. ATTRIBUTION.md + AI_USAGE.md** — AI_USAGE.md ✅ exists and is good. **ATTRIBUTION.md does not exist as a separate file.** These are two distinct required deliverables, not one combined doc.
- [ ] **8. Video** — **not started.** 5-8 min, live demo, a shown imperfection, your hardest decision, AI-tool honesty, experiment conclusion. Budget real time — this is not a 10-minute afterthought, and a broken/unlisted link is explicitly called out as "the single most common reason a good submission stalls."

---

## Part 2 — Structural gaps against the real brief (newly found, not yet fixed)

Ranked by how much they cost you if left alone:

1. **3 of 4 required KPIs don't exist yet.** You have something like DAR. **CPAD, WTR, and BC are not implemented anywhere.** B3 names all four explicitly as "must implement." This is likely the highest-value fix on this whole list — it's pure calculation over data you're already collecting, no new UI needed for the KPIs themselves.
2. **WTR can't be computed correctly even once built**, because superseded/cancelled requests currently record **zero tokens** in their trace line (checked: `cancel_request` finalizes with no token data). WTR needs to know what was spent on work that got thrown away — right now that's always reported as 0, which makes the KPI silently wrong, not just missing.
3. **Missing 2 of 6 required latency segments**: no `ttfb` (time to first byte) or `ttft` (time to first token) — you only split `t_dispatch`/`t_stream`, which conflates provider network time with generation time. Real fix, moderate effort (needs a timestamp at "request sent" and another at "first byte received," both already close to code you have).
4. **Trace schema doesn't match the documented one** — missing `session_id`, `trigger` type (`idle_pause`/`explicit`/`refine`), `effort`, `config_id`, and several `input.*` fields. Outcome enum is missing `superseded` and `timeout` as distinct values.
5. **No Markdown rendering** — brief explicitly wants "at least Markdown and LaTeX." You have LaTeX only.
6. **No keyboard shortcuts** for accept/discard/generate — "every frequent action has a shortcut, and they are discoverable" is an explicit A2/craft requirement.
7. **No frame-timing measurement at load** (5,000+ strokes) — untested, unreported.

---

## Part 3 — The honest triage for ~48 hours

Given the deliverable-gate structure and that Metrics (22) + Experiment (15) = 37 points — more than the canvas itself — here's the order I'd actually work in:

1. **Implement CPAD / WTR / BC** (even simply) + fix superseded-request token recording. Highest points-per-hour on this entire list.
2. **Add `ttfb`/`ttft`.** Real but contained — you already timestamp around this exact boundary.
3. **Build the Five Canvases, run a real (possibly reduced-N) B5 experiment, write REPORT.md.** Currently zero. A smaller, honestly-labeled N is fully fine per the brief's own "negative/limited result, honestly reported, scores full marks" rule — do not fabricate to hit 45/arm if time doesn't allow it. State the real number.
4. **Write ATTRIBUTION.md.** Cheap, currently just missing.
5. **README**: declared latency budget (one line), architecture diagram (even simple), rough frame-timing note.
6. **Record the video last**, once there's something real to demo — but don't leave it until the final hour.
7. **Explicitly write down what you're cutting** — Markdown rendering, keyboard shortcuts, full schema conformance if you don't get to all of it. The brief rewards this specifically; silence on a gap is worse than a stated one.

---

## What I'd need from you to start executing

This is a lot for 48 hours. Tell me which item you want to start on and I'll work it with you directly — I'd suggest **#1 (the KPIs)** first, since it's the highest-value, most contained piece of code and everything else in Part B depends on the trace data being right before you run the real experiment in #3.
