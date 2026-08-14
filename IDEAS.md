# IDEAS.md

## Feature Ideation

Nine canvas-related ideas were considered against the project requirements.
Each idea was evaluated for user impact, canvas-specific value, implementation
effort, model dependency, cost, and risk.

| # | Idea | Why it fits the canvas | Verdict |
|---|---|---|---|
| 1 | Model routing by region complexity | Uses spatial signals such as stroke count, ink density, and region size to choose an appropriate model. | **Selected** |
| 2 | Multi-region batching | Uses separate spatial regions to combine related requests. | Cut |
| 3 | Persistent draft memory | Uses spatial proximity to provide context from earlier work. | Cut |
| 4 | Voice-triggered capture | Useful interaction improvement, but not specifically canvas-native. | Cut |
| 5 | Confidence-scored drafts | Could communicate model uncertainty, but confidence estimates are unreliable. | Cut |
| 6 | Offline mode | General application resilience rather than a canvas-specific feature. | Cut |
| 7 | Handwriting-style transfer | Could make generated drafts visually match the user's canvas. | Cut |
| 8 | Cost-budget guardrail | Useful for controlling provider usage, but primarily a backend policy. | Cut |
| 9 | Shareable canvas links | Strong canvas use case, but requires persistence/hosting outside the project scope. | Cut |

## Selected Feature: Model Routing

**Problem:** Simple regions do not need the same model as complex regions.
Using one provider for every request can unnecessarily increase latency or
cost.

**Why canvas:** The canvas provides spatial information that can be used to
estimate region complexity, including stroke count, ink density, and bounding
box size.

**Implementation:** `backend/router.py` uses a lightweight threshold-based
heuristic to route simpler regions to the fast/local Ollama tier and more
complex regions to the heavier Gemini tier.

**Model dependency:** Low. The routing logic is independent of a specific
model and can work with different providers.

**Cost:** Very low. Routing uses information already available in the request
and does not require an additional model call.

**Risk:** The thresholds are heuristic starting points rather than a trained
classifier. They are intentionally simple and transparent.

## Selection Rationale

Model routing was selected because it directly improves the core canvas
workflow while also providing a measurable experiment variable. It reuses the
existing tracing, token, cost, and latency infrastructure, allowing the
feature to be evaluated quantitatively.

The other ideas were cut because they either had weaker canvas-specific value,
required significantly more infrastructure, introduced additional model cost
or reliability concerns, or were explicitly outside the project's scope.

Full implementation and routing thresholds are documented in
`backend/router.py`.
