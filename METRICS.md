# METRICS.md

This file is filled in as real usage happens — none of the numbers below
are placeholders dressed up as results. Where a section says "not yet
run," that's accurate as of the initial scaffold commit, not a gap being
papered over.

## Rate table — source & date

`backend/config/rates.yaml` currently ships with placeholder figures for
`gemini-3-flash` and `google/gemini-flash-1.5` (OpenRouter). **Before
trusting any cost number in this file or in `reports/REPORT.md`, verify
current pricing and update this section:**

| Model | Input $/1M | Output $/1M | Source | Verified on |
|---|---|---|---|---|
| gemini-3-flash | _TODO_ | _TODO_ | _link to provider pricing page_ | _date_ |
| qwen3-vl:4b (local) | $0 marginal | $0 marginal | n/a — local inference | n/a |
| google/gemini-flash-1.5 (OpenRouter) | _TODO_ | _TODO_ | _link_ | _date_ |

Local-model cost is genuinely $0 marginal per request, but that's not the
same as $0 total cost — electricity and GPU-hours aren't nothing. Report
latency/throughput for the local arm as the headline comparison, not a
`$0.00` line that implies it's free.

## Token estimator validation (PRD §8)

Run before filling this in:

```bash
# once you have >=20 real requests with known ground-truth image token
# counts (from a provider that returns split image/text usage):
python -c "
from estimator import validate
predictions = [...]   # your estimator's output per request
ground_truth = [...]  # provider-reported image tokens for the same requests
print(validate(predictions, ground_truth).as_dict())
"
```

| | |
|---|---|
| n | _not yet run — need n >= 20_ |
| MAE | _TODO_ |
| MAE as % of mean ground truth | _TODO_ |
| Tiling rule used | `TilingRule(tile_px=768, tokens_per_tile=258, base_tokens=0)` — **verify against the live provider docs before trusting this**, see `estimator.py` module docstring |

An honest estimator with a known error bar outscores a confident guess.
Don't round MAE down or cherry-pick the validation set — see PRD §8.

## Live panel vs. durable trace file

The in-app metrics panel (`GET /metrics/summary`) reads from the tracer's
in-memory buffer of completed requests for the current process lifetime.
`backend/traces/traces.jsonl` is the durable copy and the only source
`scripts/analyze_traces.py` reads from — the two will diverge after a
backend restart (in-memory resets, the JSONL file doesn't), which is
expected, not a bug.
