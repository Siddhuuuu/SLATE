"""
main.py — the entire backend surface. Per PRD §4:

    POST   /requests                 kick off a model call, return request_id immediately
    GET    /requests/{id}/stream     SSE: stream tokens as they arrive
    DELETE /requests/{id}            cancel / supersede an in-flight call
    POST   /requests/{id}/outcome    client reports accepted/discarded + t_render, finalizes trace

Plus one read-only endpoint the PRD's own §7.4 requires for the live panel:

    GET    /metrics/summary          cheap polling target for the in-app metrics panel

No auth, no sessions, no DB, no canvas endpoints. That's the whole app.
"""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from adapters.client import get_client, model_for
from cost import compute_cost_usd
from estimator import estimate_image_tokens
from models import (
    CreateRequestIn,
    CreateRequestOut,
    LatencySegments,
    Outcome,
    OutcomeIn,
    OutcomeOut,
    TokenUsage,
    TraceLine,
    new_request_id,
)
from router import decide as route_decide
from tracer import tracer

# request_id -> asyncio.Queue[(event_name, data_dict) | None]
_queues: dict[str, "asyncio.Queue"] = {}
# request_id -> the in-flight model-call task, so DELETE can cancel it
_tasks: dict[str, asyncio.Task] = {}

SYSTEM_PROMPT = (
    "You are an inline drafting assistant on a handwritten canvas. Given a "
    "cropped region of ink and its surrounding context, produce a short, "
    "direct completion or answer — no preamble, no restating the question."
)


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


# ---------------------------------------------------------------------------
# POST /requests
# ---------------------------------------------------------------------------

@app.post("/requests", response_model=CreateRequestOut)
async def create_request(payload: CreateRequestIn) -> CreateRequestOut:
    decision = route_decide(payload.context, provider_override=payload.provider_override)
    request_id = new_request_id()

    trace = TraceLine(
        request_id=request_id,
        provider=decision.provider,
        model=decision.model,
        tier=decision.tier,
        routing_reason=decision.reason,
        context=payload.context,
        latency=LatencySegments(t_capture_ms=payload.t_capture_ms),
    )
    tracer.start(trace)

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
        )
    )
    _tasks[request_id] = task

    return CreateRequestOut(
        request_id=request_id, tier=decision.tier, provider=decision.provider, model=decision.model
    )


async def _run_model_call(
    request_id: str,
    provider: str,
    model: str,
    image_b64: str,
    image_width_px: int | None,
    image_height_px: int | None,
    queue: "asyncio.Queue",
) -> None:
    """
    Background task: fires the provider call, streams chunks onto `queue`
    as they arrive, and updates the trace via tracer.py. Never silently
    reroutes to a different provider on failure (PRD §3) — a failure is
    logged as outcome="error" and surfaced to the client as-is.
    """
    try:
        client = get_client(provider)  # type: ignore[arg-type]
        tracer.mark_dispatch_complete(request_id)

        stream = await client.chat.completions.create(
            model=model,
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=512,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Continue/complete this handwritten region."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/webp;base64,{image_b64}"},
                        },
                    ],
                },
            ],
        )

        full_text = ""
        usage_obj = None
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_text += delta
                    await queue.put(("token", {"text": delta}))
            if getattr(chunk, "usage", None) is not None:
                usage_obj = chunk.usage

        if usage_obj is not None:
            tokens = TokenUsage(
                input_tokens=getattr(usage_obj, "prompt_tokens", None),
                output_tokens=getattr(usage_obj, "completion_tokens", None),
                total_tokens=getattr(usage_obj, "total_tokens", None),
                estimated=False,
            )
        else:
            # Provider didn't return usage on the stream — fall back to the
            # estimator for the image side (PRD §8) and leave text tokens
            # unknown rather than guessing those too.
            w = image_width_px or 1024
            h = image_height_px or 1024
            tokens = TokenUsage(image_tokens=estimate_image_tokens(w, h), estimated=True)

        tracer.mark_stream_complete(request_id, tokens=tokens)
        await queue.put(("complete", {"text": full_text}))

    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — deliberately broad: any provider failure surfaces, none are swallowed
        await queue.put(("error", {"message": str(exc)}))
        await tracer.finalize(request_id, Outcome.error, error_message=str(exc))
    finally:
        await queue.put(None)  # sentinel: stream generator stops reading
        _tasks.pop(request_id, None)


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
    task = _tasks.pop(request_id, None)
    if task is not None:
        task.cancel()
    queue = _queues.pop(request_id, None)
    if queue is not None:
        await queue.put(None)

    trace = await tracer.finalize(request_id, Outcome.cancelled)
    if trace is None:
        raise HTTPException(status_code=404, detail="unknown or already-finalized request_id")
    return {"request_id": request_id, "outcome": "cancelled"}


# ---------------------------------------------------------------------------
# POST /requests/{id}/outcome
# ---------------------------------------------------------------------------

@app.post("/requests/{request_id}/outcome", response_model=OutcomeOut)
async def report_outcome(request_id: str, payload: OutcomeIn) -> OutcomeOut:
    pending_trace = tracer.get(request_id)
    if pending_trace is None:
        raise HTTPException(status_code=404, detail="unknown or already-finalized request_id")

    cost_usd = None
    if pending_trace.tokens is not None:
        try:
            cost_usd = compute_cost_usd(
                model=pending_trace.model,
                input_tokens=pending_trace.tokens.input_tokens,
                output_tokens=pending_trace.tokens.output_tokens,
                image_tokens=pending_trace.tokens.image_tokens,
            )
        except KeyError:
            cost_usd = None  # unknown model in rate table — don't crash the outcome report over it

    outcome = Outcome.accepted if payload.outcome == "accepted" else Outcome.discarded
    trace = await tracer.finalize(
        request_id, outcome, t_render_ms=payload.t_render_ms, cost_usd=cost_usd
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
    total_cost = sum(t.get("cost_usd") or 0 for t in completed)

    render_latencies = [
        t["latency"]["t_render_ms"]
        for t in completed
        if t.get("latency") and t["latency"].get("t_render_ms") is not None
    ]
    avg_render_ms = sum(render_latencies) / len(render_latencies) if render_latencies else None

    decided = accepted + discarded
    return {
        "total_requests": len(completed),
        "in_flight": tracer.in_flight_count(),
        "accepted": accepted,
        "discarded": discarded,
        "errors": errors,
        "draft_acceptance_rate": (accepted / decided) if decided else None,
        "total_cost_usd": round(total_cost, 6),
        "avg_render_ms": round(avg_render_ms, 1) if avg_render_ms is not None else None,
        "generated_at": time.time(),
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
