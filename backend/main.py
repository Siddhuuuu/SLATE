"""
main.py — the entire backend surface. Per PRD §4 / brief A6:

    POST   /requests                 kick off a model call, return request_id immediately
    GET    /requests/{id}/stream     SSE: stream tokens as they arrive
    DELETE /requests/{id}            cancel / supersede an in-flight call
    POST   /requests/{id}/outcome    client reports accepted/discarded + t_render/e2e, finalizes trace

Plus one read-only endpoint the PRD's own §7.4 requires for the live panel:

    GET    /metrics/summary          cheap polling target for the in-app metrics panel, includes the 4 KPIs

No auth, no sessions (beyond the one process-lifetime session_id), no DB,
no canvas endpoints. That's the whole app.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from adapters.client import get_client, model_for
from cost import compute_cost_usd
from estimator import estimate_image_tokens
from kpis import compute_all_kpis, DEFAULT_LATENCY_BUDGET_MS
from models import (
    CreateRequestIn,
    CreateRequestOut,
    LatencySegments,
    Outcome,
    OutcomeIn,
    OutcomeOut,
    TokenUsage,
    TraceInput,
    TraceLine,
    new_request_id,
)
from router import decide as route_decide
from quota_guard import QuotaExceeded
from think_filter import ThinkTagStripper
from tracer import tracer

# request_id -> asyncio.Queue[(event_name, data_dict) | None]
_queues: dict[str, "asyncio.Queue"] = {}
# request_id -> the in-flight model-call task, so DELETE can cancel it
_tasks: dict[str, asyncio.Task] = {}
# request_id -> running state used to estimate partial token spend if the
# request is superseded/timed out/cancelled mid-stream — see
# _estimate_committed_tokens() and its two call sites below.
_partial_state: dict[str, dict] = {}

SYSTEM_PROMPT = (
    "You are an inline drafting assistant on a handwritten canvas. Given a "
    "cropped region of ink and its surrounding context, produce a short, "
    "direct completion or answer — no preamble, no restating the question."
)
USER_PROMPT_TEXT = "Continue/complete this handwritten region."

# Server-side request budget — a provider hang (Ollama on a loaded GPU,
# a stalled Gemini connection) must not hold a request open forever.
# Distinct from the CLIENT-declared BC latency budget in kpis.py (that one
# is "did this feel fast enough"; this one is "did this ever finish at all").
REQUEST_TIMEOUT_S = 45


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for task in _tasks.values():
        task.cancel()


app = FastAPI(title="Project SLATE backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _estimate_committed_tokens(request_id: str) -> TokenUsage | None:
    """
    Builds a best-effort TokenUsage for a request that never reached
    mark_stream_complete (superseded, timed out, cancelled). Input tokens
    are treated as fully committed the moment the provider call fired —
    providers bill input tokens regardless of how much output followed.
    Output tokens are estimated from whatever partial text had streamed
    (rough chars/4 heuristic) before the request was cut off. Without
    this, every aborted request would silently show 0 tokens, and WTR
    (wasted token ratio) would be meaningless — it exists specifically to
    measure spend on work that got thrown away.
    """
    state = _partial_state.get(request_id)
    if state is None:
        return None

    image_tokens = estimate_image_tokens(
        state.get("image_width_px") or 1024, state.get("image_height_px") or 1024
    )
    text_tokens = max(1, state.get("prompt_chars", 0) // 4)
    partial_output_tokens = max(0, state.get("partial_chars", 0) // 4)

    return TokenUsage(
        input_text_tokens=text_tokens,
        input_image_tokens=image_tokens,
        input_image_source="estimated",
        output_tokens=partial_output_tokens,
        reasoning_tokens=None,
        total_tokens=text_tokens + image_tokens + partial_output_tokens,
    )


def _cost_for_trace(trace: TraceLine) -> float | None:
    if trace.tokens is None:
        return None
    try:
        return compute_cost_usd(
            model=trace.model,
            input_text_tokens=trace.tokens.input_text_tokens,
            input_image_tokens=trace.tokens.input_image_tokens,
            output_tokens=trace.tokens.output_tokens,
            reasoning_tokens=trace.tokens.reasoning_tokens,
        )
    except KeyError:
        return None  # unknown model in rate table — don't crash the caller over it


def _cost_for_tokens(model: str, tokens: TokenUsage | None) -> float | None:
    """Same computation as _cost_for_trace, usable before a TraceLine is
    finalized — the supersede/timeout/error paths need this: they build
    an estimated TokenUsage (see _estimate_committed_tokens) but don't
    have a finalized TraceLine yet to read .model off of, since
    tracer.finalize() is what produces one. Without this, every
    superseded/timed-out/errored request would silently record
    cost_usd=null despite having real (estimated) token spend — which
    would make CPAD quietly undercount total cost."""
    if tokens is None:
        return None
    try:
        return compute_cost_usd(
            model=model,
            input_text_tokens=tokens.input_text_tokens,
            input_image_tokens=tokens.input_image_tokens,
            output_tokens=tokens.output_tokens,
            reasoning_tokens=tokens.reasoning_tokens,
        )
    except KeyError:
        return None


# ---------------------------------------------------------------------------
# POST /requests
# ---------------------------------------------------------------------------

@app.post("/requests", response_model=CreateRequestOut)
async def create_request(payload: CreateRequestIn) -> CreateRequestOut:
    try:
        decision = route_decide(payload.context, provider_override=payload.provider_override)
    except QuotaExceeded as exc:
        # Only reachable via a pinned provider_override=gemini (the auto-
        # routed path downgrades gracefully inside router.py and never
        # raises this) — a pinned request that can't safely run is a 429,
        # not a 500, and must fail loudly rather than silently substitute
        # a different provider. See router.py's decide() docstring.
        raise HTTPException(status_code=429, detail=str(exc))

    request_id = new_request_id()

    try:
        image_bytes = len(base64.b64decode(payload.image_b64))
    except Exception:
        image_bytes = 0

    prompt_chars = payload.prompt_chars or (len(SYSTEM_PROMPT) + len(USER_PROMPT_TEXT))
    effort = "low" if decision.provider.value == "gemini" else "n/a"

    trace = TraceLine(
        request_id=request_id,
        trigger=payload.trigger,
        provider=decision.provider,
        model=decision.model,
        tier=decision.tier,
        effort=effort,
        config_id=payload.config_id,
        routing_reason=decision.reason,
        context=payload.context,
        input=TraceInput(
            crop_px=(payload.image_width_px or 0, payload.image_height_px or 0),
            format="png",
            bytes=image_bytes,
            zoom=payload.context.zoom,
            stroke_count=payload.context.stroke_count,
            prompt_chars=prompt_chars,
        ),
        latency=LatencySegments(t_capture_ms=payload.t_capture_ms),
    )
    tracer.start(trace)

    _partial_state[request_id] = {
        "image_width_px": payload.image_width_px,
        "image_height_px": payload.image_height_px,
        "prompt_chars": prompt_chars,
        "partial_chars": 0,
    }

    queue: asyncio.Queue = asyncio.Queue()
    _queues[request_id] = queue

    task = asyncio.create_task(
        _run_model_call(
            request_id=request_id,
            provider=decision.provider.value if hasattr(decision.provider, "value") else decision.provider,
            model=decision.model,
            image_b64=payload.image_b64,
            image_width_px=payload.image_width_px,
            image_height_px=payload.image_height_px,
            queue=queue,
            max_tokens_override=payload.max_tokens_override,
            ollama_keep_alive=payload.ollama_keep_alive,
        )
    )
    _tasks[request_id] = task

    return CreateRequestOut(
        request_id=request_id, tier=decision.tier, provider=decision.provider, model=decision.model
    )


async def _stream_provider_call(
    request_id: str,
    provider: str,
    model: str,
    image_b64: str,
    image_width_px: int | None,
    image_height_px: int | None,
    queue: "asyncio.Queue",
    max_tokens: int,
    ollama_keep_alive: str | None,
) -> None:
    client = get_client(provider)  # type: ignore[arg-type]
    tracer.mark_dispatch_complete(request_id)

    # think=False is an Ollama-specific request field (0.6+, both
    # /api/chat and its OpenAI-compat endpoint) for reasoning-capable
    # local models. Gemini's API rejects any request containing an
    # unrecognized top-level field with a hard 400 — so this must never
    # be sent to non-Ollama providers.
    #
    # reasoning_effort is the Gemini-side equivalent, with one hard
    # difference confirmed against Google's own docs: thinking CANNOT be
    # fully disabled on Gemini 2.5 Pro or any Gemini 3.x model — "low" is
    # the minimum, not "off". Same reasoning applies: never send an
    # Ollama-only or Gemini-only param to the other provider.
    #
    # keep_alive is Optimization A (B5): keeps the model resident between
    # requests instead of Ollama unloading it, avoiding a reload's latency
    # on the next call. Only meaningful for Ollama, and only sent when the
    # caller explicitly asked for it (ollama_keep_alive is not None) —
    # baseline/"off" means Ollama's own default behavior applies
    # untouched, not this app silently picking a value for it.
    extra_kwargs: dict = {}
    if provider == "ollama":
        extra_body: dict = {"think": False}
        if ollama_keep_alive is not None:
            extra_body["keep_alive"] = ollama_keep_alive
        extra_kwargs["extra_body"] = extra_body
    elif provider == "gemini":
        extra_kwargs["reasoning_effort"] = "low"

    stream = await client.chat.completions.create(
        model=model,
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT_TEXT},
                    {
                        "type": "image_url",
                        # Frontend crops are PNG (see roi.ts — Ollama's Go
                        # image backend can't decode WebP).
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            },
        ],
        **extra_kwargs,
    )

    full_text = ""
    usage_obj = None
    think_filter = ThinkTagStripper()
    seen_first_chunk = False

    async for chunk in stream:
        if not seen_first_chunk:
            tracer.mark_first_byte(request_id)
            seen_first_chunk = True

        if chunk.choices:
            delta_obj = chunk.choices[0].delta
            # Reasoning-capable models stream two separate channels:
            # delta.content (the actual answer) and delta.reasoning
            # (internal chain-of-thought). These must never be merged —
            # only delta.content is ever shown.
            raw_delta = delta_obj.content or ""
            # Separately: some models write literal <think>...</think>
            # tags AS TEXT inside delta.content itself. Confirmed with
            # qwen3-vl over Ollama even with think=False requested.
            delta = think_filter.feed(raw_delta) if raw_delta else ""
            if delta:
                if not full_text:
                    tracer.mark_first_content_token(request_id)
                full_text += delta
                state = _partial_state.get(request_id)
                if state is not None:
                    state["partial_chars"] = len(full_text)
                await queue.put(("token", {"text": delta}))
        if getattr(chunk, "usage", None) is not None:
            usage_obj = chunk.usage

    trailing = think_filter.flush()
    if trailing:
        if not full_text:
            tracer.mark_first_content_token(request_id)
        full_text += trailing
        await queue.put(("token", {"text": trailing}))

    tokens = _build_token_usage(usage_obj, image_width_px, image_height_px)
    tracer.mark_stream_complete(request_id, tokens=tokens)
    await queue.put(("complete", {"text": full_text}))


def _build_token_usage(usage_obj, image_width_px: int | None, image_height_px: int | None) -> TokenUsage:
    """
    No provider currently in use (Gemini via OpenAI-compat, Ollama)
    reports a real text/image token split — confirmed via
    scripts/validate_image_token_estimator.py's sanity check. So
    input_image_tokens ALWAYS comes from estimator.py right now, and
    input_text_tokens is back-calculated as whatever's left of the
    provider's combined prompt_tokens after subtracting that estimate.
    input_image_source stays "estimated" until a real split is confirmed
    available (see that script's docstring for what would need to change).

    reasoning_tokens: some providers (confirmed: Gemini) bill hidden
    thinking tokens as part of total_tokens without exposing them in
    input/output — the gap between total_tokens and (prompt+completion)
    is attributed here explicitly, rather than silently folded into
    output the way an earlier version of cost.py did.
    """
    w = image_width_px or 1024
    h = image_height_px or 1024
    image_tokens = estimate_image_tokens(w, h)

    if usage_obj is None:
        return TokenUsage(
            input_image_tokens=image_tokens,
            input_image_source="estimated",
        )

    prompt_tokens = getattr(usage_obj, "prompt_tokens", None)
    completion_tokens = getattr(usage_obj, "completion_tokens", None)
    total_tokens = getattr(usage_obj, "total_tokens", None)

    text_tokens = None
    if prompt_tokens is not None:
        text_tokens = max(0, prompt_tokens - image_tokens)

    reasoning_tokens = None
    if total_tokens is not None:
        accounted = (text_tokens or 0) + image_tokens + (completion_tokens or 0)
        if total_tokens > accounted:
            reasoning_tokens = total_tokens - accounted

    return TokenUsage(
        input_text_tokens=text_tokens,
        input_image_tokens=image_tokens,
        input_image_source="estimated",
        output_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
    )


DEFAULT_MAX_TOKENS = 512  # baseline for Optimization B — capped max_tokens, see CreateRequestIn


async def _run_model_call(
    request_id: str,
    provider: str,
    model: str,
    image_b64: str,
    image_width_px: int | None,
    image_height_px: int | None,
    queue: "asyncio.Queue",
    max_tokens_override: int | None = None,
    ollama_keep_alive: str | None = None,
) -> None:
    """
    Background task: fires the provider call, streams chunks onto `queue`
    as they arrive, and updates the trace via tracer.py. Never silently
    reroutes to a different provider on failure (PRD §3) — a failure is
    logged as outcome="error" (or "timeout") and surfaced to the client
    as-is.
    """
    max_tokens = max_tokens_override or DEFAULT_MAX_TOKENS
    tracer.set_optimization_config(request_id, max_tokens_used=max_tokens, ollama_keep_alive_used=ollama_keep_alive)

    try:
        await asyncio.wait_for(
            _stream_provider_call(
                request_id,
                provider,
                model,
                image_b64,
                image_width_px,
                image_height_px,
                queue,
                max_tokens=max_tokens,
                ollama_keep_alive=ollama_keep_alive,
            ),
            timeout=REQUEST_TIMEOUT_S,
        )

    except asyncio.CancelledError:
        raise  # supersede/DELETE path — handled in cancel_request, not here

    except asyncio.TimeoutError:
        tokens = _estimate_committed_tokens(request_id)
        await queue.put(("error", {"message": f"Request exceeded the {REQUEST_TIMEOUT_S}s budget"}))
        await tracer.finalize(
            request_id,
            Outcome.timeout,
            error_message=f"Exceeded {REQUEST_TIMEOUT_S}s request budget",
            tokens=tokens,
            cost_usd=_cost_for_tokens(model, tokens),
        )

    except Exception as exc:  # noqa: BLE001 — deliberately broad: any provider failure surfaces, none are swallowed
        tokens = _estimate_committed_tokens(request_id)
        await queue.put(("error", {"message": str(exc)}))
        await tracer.finalize(
            request_id,
            Outcome.error,
            error_message=str(exc),
            tokens=tokens,
            cost_usd=_cost_for_tokens(model, tokens),
        )

    finally:
        await queue.put(None)  # sentinel: stream generator stops reading
        _tasks.pop(request_id, None)
        _partial_state.pop(request_id, None)


# ---------------------------------------------------------------------------
# GET /requests/{id}/stream  (SSE)
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/requests/{request_id}/stream")
async def stream_request(request_id: str) -> StreamingResponse:
    queue = _queues.get(request_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="unknown or already-completed request_id")

    async def event_generator():
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event_name, data = item
                yield _sse(event_name, data)
        finally:
            _queues.pop(request_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# DELETE /requests/{id}  — cancel / supersede
# ---------------------------------------------------------------------------

@app.delete("/requests/{request_id}")
async def cancel_request(request_id: str) -> dict:
    tokens = _estimate_committed_tokens(request_id)

    pending_trace = tracer.get(request_id)  # peek before finalize() pops it, need .model for cost
    cost_usd = _cost_for_tokens(pending_trace.model, tokens) if pending_trace else None

    task = _tasks.pop(request_id, None)
    if task is not None:
        task.cancel()
    queue = _queues.pop(request_id, None)
    if queue is not None:
        await queue.put(None)
    _partial_state.pop(request_id, None)

    # This app's only real caller of DELETE today is
    # useDraftLifecycle.ts's supersedeActive() — a new capture replacing
    # an unsettled draft. Outcome.superseded (not a generic "cancelled")
    # per the brief's own definition: "A new request supersedes an
    # in-flight one; the superseded call is aborted, not orphaned — and
    # its cost is still recorded." That's exactly what `tokens`/`cost_usd`
    # here are for — without them every superseded request would silently
    # show cost_usd=null despite having real (estimated) spend, which
    # would make CPAD quietly undercount total cost.
    trace = await tracer.finalize(request_id, Outcome.superseded, tokens=tokens, cost_usd=cost_usd)
    if trace is None:
        raise HTTPException(status_code=404, detail="unknown or already-finalized request_id")
    return {"request_id": request_id, "outcome": "superseded"}


# ---------------------------------------------------------------------------
# POST /requests/{id}/outcome
# ---------------------------------------------------------------------------

@app.post("/requests/{request_id}/outcome", response_model=OutcomeOut)
async def report_outcome(request_id: str, payload: OutcomeIn) -> OutcomeOut:
    pending_trace = tracer.get(request_id)
    if pending_trace is None:
        raise HTTPException(status_code=404, detail="unknown or already-finalized request_id")

    cost_usd = _cost_for_trace(pending_trace)

    outcome = Outcome.accepted if payload.outcome == "accepted" else Outcome.discarded
    trace = await tracer.finalize(
        request_id,
        outcome,
        t_render_ms=payload.t_render_ms,
        e2e_ms=payload.e2e_ms,
        cost_usd=cost_usd,
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="request already finalized")

    return OutcomeOut(request_id=request_id, outcome=outcome, trace_written=True)


# ---------------------------------------------------------------------------
# GET /metrics/summary — read-only, powers the live panel (PRD §7.4)
# ---------------------------------------------------------------------------

@app.get("/metrics/summary")
async def metrics_summary() -> dict:
    completed = tracer.read_all_completed()
    accepted = sum(1 for t in completed if t.get("outcome") == "accepted")
    discarded = sum(1 for t in completed if t.get("outcome") == "discarded")
    errors = sum(1 for t in completed if t.get("outcome") == "error")
    superseded = sum(1 for t in completed if t.get("outcome") == "superseded")
    timeouts = sum(1 for t in completed if t.get("outcome") == "timeout")
    total_cost = sum(t.get("cost_usd") or 0 for t in completed)

    render_latencies = [
        t["latency"]["t_render_ms"]
        for t in completed
        if t.get("latency") and t["latency"].get("t_render_ms") is not None
    ]
    avg_render_ms = sum(render_latencies) / len(render_latencies) if render_latencies else None

    kpis = compute_all_kpis(completed, budget_ms=DEFAULT_LATENCY_BUDGET_MS)

    return {
        "total_requests": len(completed),
        "in_flight": tracer.in_flight_count(),
        "accepted": accepted,
        "discarded": discarded,
        "errors": errors,
        "superseded": superseded,
        "timeouts": timeouts,
        "total_cost_usd": round(total_cost, 6),
        "avg_render_ms": round(avg_render_ms, 1) if avg_render_ms is not None else None,
        "kpis": kpis.as_dict(),
        "generated_at": time.time(),
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}