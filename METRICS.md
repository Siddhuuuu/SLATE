# Project SLATE — Metrics and Measurement Methodology

## Purpose

This document defines how the reported metrics should be interpreted and how the final numbers were produced.

The goal is to keep the evaluation reproducible and to distinguish:

1. accumulated system telemetry,
2. controlled provider comparisons, and
3. controlled optimization experiments.

Those are related, but they are not interchangeable.

---

## 1. Trace source

The primary raw measurement source is:

```text
backend/traces/traces.jsonl
```

Each trace contains fields for:

- request ID
- session ID
- timestamp
- provider
- model
- configuration ID
- routing reason
- request context
- input characteristics
- token counts
- latency measurements
- cost
- outcome
- error message
- retry count

The analyzer consumes these traces and generates:

```text
reports/summary.csv
reports/REPORT.md
reports/latency_by_arm.png
reports/cost_by_arm.png
reports/time_trend.png
```

---

## 2. Configuration IDs

Configuration IDs are the key mechanism for separating experiment conditions.

Examples:

```text
cfg_gemini
cfg_ollama

cfg_gemini_ka30m
cfg_gemini_kaoff
cfg_ollama_ka30m
cfg_ollama_kaoff

cfg_gemini_mtok256
cfg_gemini_mtok512
cfg_ollama_mtok256
cfg_ollama_mtok512
```

The analyzer groups traces by `config_id`.

This is preferable to inferring experimental conditions from timestamps or environment variables after the fact.

---

## 3. Number of observations

For each configuration:

- `n` is the number of trace records.
- `n_with_e2e` is the number of records with a usable E2E latency value.

A timeout can therefore appear in `n` without contributing a normal E2E observation.

This is intentional.

Failures should remain visible in the denominator/history rather than being deleted because they make the latency distribution inconvenient.

---

## 4. E2E latency

E2E latency represents the end-to-end time recorded by the tracing system for a request.

The report exposes:

- p50 E2E — median latency
- p95 E2E — tail latency
- max E2E — maximum observed latency

### Why p50 and p95?

p50 answers:

> "What does a typical successful request feel like?"

p95 answers:

> "How bad is the slow tail?"

For an interactive AI system, p95 is especially important because occasional long stalls can dominate user experience even when the median is acceptable.

---

## 5. Draft Acceptance Rate

DAR is reported as:

```text
accepted drafts / relevant draft outcomes
```

The final session summary reports:

```text
DAR = 96.12%
```

A high DAR means that most instrumented requests reached an accepted-draft outcome according to the system's trace semantics.

DAR should not be interpreted as model factual accuracy. It is a **system outcome metric**, not a human correctness score.

---

## 6. Wasted Token Ratio

WTR measures token usage associated with requests that the tracing system considers wasted.

The final session summary reports:

```text
WTR = 8.59%
```

This metric is important for an interactive system because superseded/cancelled work can consume compute even when its result is no longer needed.

WTR should therefore be interpreted as an efficiency/cancellation metric, not as a model-quality metric.

---

## 7. Budget Compliance

The configured budget is:

```text
p95 E2E <= 8000 ms
```

The final session summary reports:

```text
BC = 54.64%
```

Budget Compliance therefore reflects how much of the measured workload satisfies the defined latency target.

The result should be reported honestly: the current system does not yet consistently satisfy the desired interactive latency budget.

---

## 8. CPAD

CPAD means:

```text
Cost Per Accepted Draft
```

The generated session summary reports approximately:

```text
$0.000003
```

This value is dependent on the trace cost fields and the analyzer's accounting rules.

A missing provider cost field must not be interpreted as a zero-cost API call.

---

## 9. Token measurements

The trace system records:

- input text tokens
- estimated input image tokens
- output tokens
- reasoning tokens when available
- cache-read tokens
- total tokens

The image-token field is explicitly marked as estimated in the trace data.

Therefore, image-token values should be described as estimates rather than exact provider-billed image-token counts.

---

## 10. Cost methodology

Ollama runs are local and are recorded with:

```text
cost_usd = 0
```

This means zero direct API charge in the trace accounting. It does not mean the local inference has zero electricity, hardware, or opportunity cost.

Gemini cost fields are not consistently populated in the current aggregate output.

For a provider-rate estimate, Gemini 3.5 Flash-Lite's published rates should be applied to the recorded token counts:

```text
input:  $0.30 / 1M tokens
output: $2.50 / 1M tokens
```

This estimate should be presented separately from trace-recorded provider cost.

---

## 11. Experimental controls

The controlled experiments use:

- five benchmark crops
- maximum image dimension of 1024 px
- interleaved request ordering
- fixed experiment configuration per request
- 10 requests per condition
- 15-second cooldown

The interleaving is important because it reduces the risk that one provider is always measured at a different point in the run.

---

## 12. Statistical caution

The controlled optimization sample is:

```text
n = 10 per condition
```

Therefore:

- report medians and tail statistics,
- show the raw sample count,
- avoid claiming statistical significance,
- avoid claiming universal behavior,
- describe the results as measured effects in this benchmark.

The conclusions are engineering conclusions from observed distributions, not claims about the providers under every workload.

---

## 13. Historical traces

The raw JSONL intentionally contains earlier exploratory runs.

Two early Gemini traces used:

```text
gemini-3.1-flash-lite
```

and timed out at:

```text
Exceeded 45s request budget
```

Later controlled experiments used:

```text
gemini-3.5-flash-lite
```

Those model configurations are separated conceptually even though the raw trace file is append-only.

This preserves experimental history and prevents accidental erasure of failures.

---

## 14. Reproducibility

Run:

```bash
python3 scripts/analyze_traces.py
```

to regenerate the report from the trace file.

The report is therefore generated from machine-readable telemetry rather than manually typed numbers.
