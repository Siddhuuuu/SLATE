# METRICS.md

Filled in as real usage happens — sections marked "not yet run" are
accurate as of this commit, not a gap being papered over.

## Trace schema

One JSON object per line, appended atomically, in `backend/traces/traces.jsonl`.
Matches the brief's documented schema field-for-field — see `backend/models.py`
for the authoritative Pydantic definitions.

```json
{
  "request_id": "req_00a906d0bb6a",
  "session_id": "ses_a1b2c3d4e5f6",
  "created_at": "2026-08-12T19:47:24.914205+00:00",
  "trigger": "idle_pause",
  "provider": "gemini",
  "model": "gemini-3.6-flash",
  "tier": "heavy",
  "effort": "low",
  "config_id": "cfg_gemini",
  "routing_reason": "ink_density 0.22 <= 0.35",
  "outcome": "accepted",
  "context": { "bbox": {"...": "..."}, "zoom": 1.0, "stroke_count": 7 },
  "input": {
    "crop_px": [922, 307], "format": "png", "bytes": 41200,
    "zoom": 1.0, "stroke_count": 7, "prompt_chars": 143
  },
  "tokens": {
    "input_text_tokens": 874, "input_image_tokens": 258,
    "input_image_source": "estimated",
    "output_tokens": 17, "reasoning_tokens": 198,
    "cache_read_tokens": 0, "total_tokens": 1347
  },
  "latency_ms": {
    "t_capture": 24.0, "t_dispatch": 75.8,
    "ttfb": 620.1, "ttft": 3210.4,
    "t_stream": 405.7, "t_render": 91.3, "e2e": 4407.3
  },
  "cost_usd": 0.000163,
  "error": null,
  "retries": 0
}
```

## Latency segments

| Symbol | Starts | Ends | Measured |
|---|---|---|---|
| `t_capture` | Trigger fires (client) | Payload encoded | client, `roi.ts` |
| `t_dispatch` | Payload received (server) | Provider call fired | server, `tracer.mark_dispatch_complete` |
| `ttfb` | Provider call fired | First byte of any kind received | server, `tracer.mark_first_byte` |
| `ttft` | Provider call fired | First **content** token (post think-filter) | server, `tracer.mark_first_content_token` |
| `t_stream` | First content token | Last content token | server, `tracer.mark_stream_complete` |
| `t_render` | Last content token | Draft painted on canvas | client, `useDraftLifecycle.ts` |
| `e2e` | Trigger fires | Draft painted on canvas | client, measured **directly** as one stopwatch, not summed from parts (ttfb/ttft overlap) |

**Why ttft can be much larger than ttfb, and why that's the point, not a
bug**: for a reasoning-capable model, the provider connection opens
quickly (low ttfb) but the model may spend real time on hidden reasoning
before emitting visible content (high ttft). This project found exactly
this empirically — see `AI_USAGE.md`'s entry on the `<think>` tag leak
and the 198-token reasoning gap found in a real Gemini trace.

## Token accounting

`input_image_source` is `"estimated"` for every trace produced so far —
confirmed via `scripts/validate_image_token_estimator.py`'s sanity check
that neither Gemini's OpenAI-compat endpoint nor Ollama's usage object
splits text/image tokens. It becomes `"reported"` only where a provider
genuinely exposes that split (see that script for the one path found so
far: Gemini's *native* SDK, `usage_metadata.prompt_tokens_details` —
unconfirmed whether that field actually populates until the script's
mandatory `--sanity-check` step is run for real).

`reasoning_tokens` is back-calculated as `total_tokens - (text + image +
output)` when a provider's `total_tokens` doesn't match the sum of its
other reported fields — this is exactly what surfaced Gemini's 198
hidden reasoning tokens in a real trace.

## Cost formula

Follows the brief's exact literal formula (`backend/cost.py`):

```
cost = (in × rate_in + out × rate_out + reasoning × rate_out) / 1,000,000
```

Where `in` = `input_text_tokens + input_image_tokens`, billed at one input
rate (the brief's formula gives image tokens no separate rate).
`reasoning_tokens` billed at the output rate.

### Rate table — source & date

`backend/config/rates.yaml` currently ships with **placeholder** figures
for Gemini models. **Verify against ai.google.dev/gemini-api/docs/pricing
before trusting any cost number in this file or REPORT.md** — not yet done.

| Model | Input $/1M | Output $/1M | Source | Verified on |
|---|---|---|---|---|
| gemini-3.6-flash | 0.075 (placeholder) | 0.30 (placeholder) | _TODO_ | _not yet_ |
| qwen3-vl:4b-instruct (local) | $0 marginal | $0 marginal | n/a — local inference | n/a |

Local-model cost is genuinely $0 marginal per request, but not $0 total
cost (electricity, GPU-hours) — report latency/throughput as the
headline comparison for the local arm, not a `$0.00` line that implies
it's free.

## The four required KPIs

Implemented as pure, tested functions in `backend/kpis.py` (17 unit
tests, including every zero-denominator edge case), computed live in
`GET /metrics/summary` and in `scripts/analyze_traces.py`'s REPORT.md
generation — one implementation, two call sites, never two formulas.

| KPI | Formula | Why |
|---|---|---|
| **CPAD** | total spend ÷ drafts accepted | Cost-per-request rewards cheap, useless answers; this doesn't |
| **DAR** | accepted ÷ (accepted + discarded) | The only in-app signal of answer quality |
| **WTR** | tokens on {discarded, cancelled, superseded, timeout, error} ÷ all tokens | What the trigger policy costs for nothing |
| **BC** | share of requests with `e2e_ms` ≤ declared budget (8000ms) | Declaring a target and measuring against it |

WTR depends on aborted requests actually recording partial token spend —
see `main.py`'s `_estimate_committed_tokens()`: input tokens are treated
as fully committed the moment a provider call fires (providers bill input
regardless of output), output tokens are a rough chars/4 estimate of
whatever streamed before the abort. Without this, every superseded/timed-out
request would silently show 0 tokens and WTR would be meaningless.

## Token estimator validation (image-token MAE)

**Not yet run.** `scripts/validate_image_token_estimator.py` is built,
bug-fixed (the original draft's `estimate_image_tokens()` call signature
was wrong — caught by actually running it, not just reading it — see
`AI_USAGE.md`), and has a mandatory `--sanity-check` step that must pass
before the real batch run.

| | |
|---|---|
| n | _not yet run — need n ≥ 20_ |
| MAE | _TODO_ |
| Tiling rule used | `TilingRule(tile_px=768, tokens_per_tile=258, base_tokens=0)` — unverified against live provider docs, see `estimator.py`'s module docstring |

## Live panel vs. durable trace file

The in-app metrics panel (`GET /metrics/summary`) reads from the tracer's
in-memory buffer of completed requests for the current process lifetime,
plus the four KPIs computed fresh on each poll. `backend/traces/traces.jsonl`
is the durable copy and the only source `scripts/analyze_traces.py` reads
from — the two diverge after a backend restart (in-memory resets, the
JSONL file doesn't), which is expected, not a bug.

**Panel screenshot: _pending — capture once the app is running with real
trace data, per the deliverables list._**
