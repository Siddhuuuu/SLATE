# VIDEO_SCRIPT.md — 5-8 min, not word-for-word, hit these beats

Don't script it verbatim — the brief explicitly says they'd rather hear
you think. Use this as a checklist of beats and rough timing, in your
own words. Record screen + webcam (just for the intro), single take is
fine.

---

## 0:00–0:30 — Who you are
Name, where you're studying, what you're interested in. Genuinely 30
seconds, don't overthink this part.

## 0:30–1:30 — What you built, and why that
- An AI canvas: draw/write, pause, a draft appears near your ink, accept
  or discard it.
- The choices you made and why: tldraw for the canvas core (so you could
  put real time into the metrics layer instead — 37 of 100 points there
  vs. 25 for canvas), a two-tier router (local Ollama for simple regions,
  Gemini for complex ones) as your one shipped feature, because it's
  simultaneously a real decision system AND your B5 experiment variable.

## 1:30–4:00 — Show it actually working (live, not slides)
- Draw something — literally draw it on camera, let the idle timer fire,
  show the placeholder appear immediately, streaming in.
- Show the router actually choosing differently for a simple vs. complex
  region (point at the `provider · tier` label on the draft card).
- Accept a draft, discard one.
- Open the metrics panel — show the live KPIs (CPAD, DAR, WTR, BC)
  actually updating, not just existing.
- **Use "Generate now" and mention the keyboard shortcuts out loud**
  (`Ctrl/⌘+Enter`, `Enter`/`Esc` to accept/discard) — the brief checks
  discoverability specifically.

## 4:00–4:45 — Show something that isn't perfect
Genuinely important, don't skip or soften this. Good honest options from
this actual build, pick one or two:
- The `<think>` tag leak you found and fixed — show the before (raw
  reasoning dumped into a draft) if you still have that screenshot, then
  the fix.
- The Five Canvases not existing yet / experiment being smaller-N than
  the brief's ideal 45/arm, if that's still true when you record — say
  the real number, not a rounded-up one.
- The Gemini model getting retired mid-build (`gemini-2.5-flash` → had
  to switch to `gemini-3.6-flash`) — a real example of the "systems
  thinking" the brief asks about: providers change under you, your
  architecture has to expect that, not be surprised by it.

## 4:45–5:45 — Your hardest decision: context extraction
What you actually send to the model and why — this is one of the two
questions they always ask, so give it real time:
- Priority order: explicit selection > recent-ink cluster (a *simple*
  bounding-box union, not fancy clustering — mention you deliberately
  simplified this after an earlier distance-threshold version silently
  dropped strokes that were far apart, e.g. writing "E" then "mc²" with
  normal spacing) > viewport fallback.
- Padding, resolution cap, why PNG not WebP (Ollama's image backend
  can't decode WebP — a real bug you found by testing, not a
  spec-reading decision).
- What non-image context rides along: bbox, zoom, stroke count, nearby
  accepted drafts.

## 5:45–6:45 — Where AI tools helped, and where they were wrong
Say the SPECIFIC thing out loud, don't gesture at "AI helped a lot."
Real, concrete examples from this actual build:
- Wrong: an early main.py sent an Ollama-only parameter (`think: false`)
  unconditionally to every provider — Gemini's API 400'd on it because
  it doesn't recognize that field. Caught by actually running it against
  a live Gemini key, not by reading the code.
- Wrong: guessed at a tldraw API (`editor.toImage`) that didn't exist in
  the installed version — caught by the build failing, fixed by reading
  tldraw's actual source in `node_modules`.
- Helped: the KPI module (CPAD/WTR/BC) — mechanical, well-specified pure
  functions, exactly where AI assistance is strong, verified with 17
  tests covering every zero-denominator edge case.

## 6:45–7:45 — Experiment conclusion + what's next with 2 more weeks
- State your real p50/p95 e2e and CPAD numbers (from REPORT.md, once run).
- If the experiment is smaller-N than ideal because of quota limits, say
  that plainly — and say what you'd do with 2 more weeks: complete the
  Five Canvases, run the full 45/arm protocol, finish the estimator MAE
  validation, and — name one real next feature from your cut list in
  IDEAS.md (e.g. the shareable canvas link, and why it lost only because
  of the brief's explicit no-hosting rule, not because the idea was weak).

## 7:45–8:00 — Close
Thanks, contact info if relevant, done.

---

## Before you hit record

- [ ] Open the video link in a private browser window and confirm it
      actually plays — the brief calls this out as the single most
      common reason a good submission stalls.
- [ ] Have the metrics panel already populated with a few real requests
      before recording, so you're not staring at empty state on camera.
- [ ] Know your real headline numbers (p50 e2e, p95 e2e, CPAD) — you
      need these in the submission email too, not just the video.
