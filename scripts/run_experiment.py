#!/usr/bin/env python3
"""
scripts/run_experiment.py

Two related but distinct jobs, both using the same interleaved-request
mechanics:

1. THE B5 CORE EXPERIMENT — compare provider arms (--arms gemini,ollama).
2. THE TWO REQUIRED OPTIMIZATIONS — compare an optimization on vs. off
   (--max-tokens / --keep-alive flags below), measured with the SAME
   protocol.

Both are pinned per-request (never via env-var-plus-restart) specifically
so arms can be interleaved — a restart-based toggle would force
all-baseline-then-all-optimized, which is exactly the contamination
pattern the brief warns against for provider arms, and there's no
principled reason to accept that risk here just because it's a different
kind of arm.

Each request gets a config_id tying it to its arm — analyze_traces.py
groups by this field.

USAGE — B5 core experiment (provider comparison):
    python scripts/run_experiment.py \
        --crops-dir traces/benchmark_crops/ \
        --arms gemini,ollama \
        --requests-per-arm 45

USAGE — Optimization A: Ollama keep_alive, before vs. after
    (pass BOTH a baseline and an optimized value; the harness interleaves
    them across the same arm exactly like it interleaves provider arms):
    python scripts/run_experiment.py \
        --crops-dir traces/benchmark_crops/ \
        --arms ollama \
        --requests-per-arm 25 \
        --keep-alive-compare "" 30m

USAGE — Optimization B: capped max_tokens, before vs. after:
    python scripts/run_experiment.py \
        --crops-dir traces/benchmark_crops/ \
        --arms ollama,gemini \
        --requests-per-arm 25 \
        --max-tokens-compare 512 256

Each file in --crops-dir should be a .png crop. --synthetic N generates N
solid-color placeholder crops to exercise the harness before real
benchmark canvases exist.
"""
from __future__ import annotations

import argparse
import base64
import io
import random
import time
from pathlib import Path

import httpx

try:
    from PIL import Image
except ImportError:  # Pillow is optional — only needed for --synthetic
    Image = None


def make_synthetic_crop(seed: int) -> bytes:
    if Image is None:
        raise RuntimeError("Pillow not installed — `pip install pillow` to use --synthetic")
    random.seed(seed)
    img = Image.new(
        "RGB", (512, 512), (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def load_crops(crops_dir: Path | None, synthetic: int) -> list[bytes]:
    if synthetic:
        return [make_synthetic_crop(i) for i in range(synthetic)]
    if crops_dir is None:
        raise ValueError("Provide --crops-dir or --synthetic N")
    files = sorted(crops_dir.glob("*.png"))
    if not files:
        raise FileNotFoundError(f"No .png files found in {crops_dir}")
    return [f.read_bytes() for f in files]


def build_request_body(
    crop_bytes: bytes,
    arm: str,
    config_id: str,
    max_tokens_override: int | None,
    ollama_keep_alive: str | None,
) -> dict:
    body = {
        "image_b64": base64.b64encode(crop_bytes).decode("ascii"),
        "image_width_px": 512,
        "image_height_px": 512,
        "context": {
            "bbox": {"x": 0, "y": 0, "width": 512, "height": 512},
            "zoom": 1.0,
            "source": "ink_cluster",
            "stroke_count": 12,
            "ink_density": 0.2,
        },
        "t_capture_ms": 15.0,
        "trigger": "explicit",  # harness-driven, not idle-timer — most honest label available
        "config_id": config_id,
        "provider_override": arm,
    }
    if max_tokens_override is not None:
        body["max_tokens_override"] = max_tokens_override
    if ollama_keep_alive is not None:
        body["ollama_keep_alive"] = ollama_keep_alive
    return body


def run_one(
    client: httpx.Client,
    backend: str,
    crop_bytes: bytes,
    arm: str,
    config_id: str,
    max_tokens_override: int | None,
    ollama_keep_alive: str | None,
) -> dict:
    body = build_request_body(crop_bytes, arm, config_id, max_tokens_override, ollama_keep_alive)
    t0 = time.monotonic()
    resp = client.post(f"{backend}/requests", json=body, timeout=30)
    resp.raise_for_status()
    created = resp.json()
    request_id = created["request_id"]

    # Drain the SSE stream to completion (simplest correct client: block
    # until the "complete" or "error" event, or the connection closes).
    with client.stream("GET", f"{backend}/requests/{request_id}/stream", timeout=60) as stream_resp:
        for line in stream_resp.iter_lines():
            if line.startswith("event: complete") or line.startswith("event: error"):
                pass  # next line carries the data payload; we don't need it here

    elapsed_ms = (time.monotonic() - t0) * 1000  # harness stands in for the client's e2e/render timer
    outcome_resp = client.post(
        f"{backend}/requests/{request_id}/outcome",
        json={"outcome": "accepted", "t_render_ms": elapsed_ms, "e2e_ms": elapsed_ms},
        timeout=30,
    )
    outcome_resp.raise_for_status()
    return {"request_id": request_id, "arm": arm, "config_id": config_id, "outcome": outcome_resp.json()}


def build_schedule(
    arms: list[str], requests_per_arm: int, max_tokens_values: list, keep_alive_values: list
) -> list[dict]:
    """
    Builds the full interleaved schedule. Every combination of
    (arm x optimization-lever-value) becomes its own config_id-tagged
    condition, and every condition contributes requests_per_arm requests,
    all interleaved round-robin together — never block-by-block, whether
    the axis being varied is provider or an optimization lever.
    """
    conditions = []
    for arm in arms:
        for mt in max_tokens_values:
            for ka in keep_alive_values:
                suffix_parts = [arm]
                if len(max_tokens_values) > 1:
                    suffix_parts.append(f"mtok{mt}")
                if len(keep_alive_values) > 1:
                    suffix_parts.append(f"ka{ka or 'off'}")
                config_id = "cfg_" + "_".join(suffix_parts)
                conditions.append(
                    {"arm": arm, "config_id": config_id, "max_tokens": mt, "keep_alive": ka}
                )

    schedule = []

    random.shuffle(conditions)

    for _ in range(requests_per_arm):
        schedule.extend(conditions)

    return schedule


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crops-dir", type=Path, default=None)
    parser.add_argument("--synthetic", type=int, default=0, help="generate N placeholder crops instead")
    parser.add_argument("--arms", type=str, required=True, help="comma-separated, e.g. gemini,ollama")
    parser.add_argument("--requests-per-arm", type=int, default=45)
    parser.add_argument("--backend", type=str, default="http://localhost:8000")
    parser.add_argument(
        "--cooldown-s", type=float, default=0.0, help="pause between requests — thermal-throttle note"
    )
    parser.add_argument(
        "--max-tokens-compare",
        nargs="+",
        type=int,
        default=[None],
        metavar="N",
        help="Optimization B: one or more max_tokens values to compare, e.g. --max-tokens-compare 512 256. "
        "Default is baseline only (no override sent).",
    )
    parser.add_argument(
        "--keep-alive-compare",
        nargs="+",
        type=str,
        default=[None],
        metavar="VALUE",
        help='Optimization A: one or more Ollama keep_alive values to compare, e.g. --keep-alive-compare "" 30m '
        '(pass an empty string for "not set" if you need it alongside a real value; omit the flag entirely '
        "for baseline-only).",
    )
    args = parser.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if len(arms) < 2 and len(args.max_tokens_compare) < 2 and len(args.keep_alive_compare) < 2:
        raise SystemExit(
            "Need either >=2 provider arms, or >=2 values in --max-tokens-compare / "
            "--keep-alive-compare to actually compare anything."
        )

    crops = load_crops(args.crops_dir, args.synthetic)
    keep_alive_values = [v if v else None for v in args.keep_alive_compare]

    schedule = build_schedule(arms, args.requests_per_arm, args.max_tokens_compare, keep_alive_values)

    print(f"Running {len(schedule)} requests across {len(set(c['config_id'] for c in schedule))} condition(s), interleaved.")
    for config_id in sorted(set(c["config_id"] for c in schedule)):
        print(f"  {config_id}")
    print("These config_ids are what REPORT.md will group by.")

    results = []
    with httpx.Client() as client:
        for i, cond in enumerate(schedule):
            crop = crops[i % len(crops)]
            try:
                result = run_one(
                    client,
                    args.backend,
                    crop,
                    cond["arm"],
                    cond["config_id"],
                    cond["max_tokens"],
                    cond["keep_alive"],
                )
                results.append(result)
                print(f"[{i + 1}/{len(schedule)}] {cond['config_id']} ok")
            except Exception as exc:  # noqa: BLE001 — log and keep going, don't let one failure kill the run
                print(f"[{i + 1}/{len(schedule)}] {cond['config_id']} FAILED: {exc}")
            if args.cooldown_s:
                time.sleep(args.cooldown_s)

    print(f"Done. {len(results)}/{len(schedule)} requests completed successfully.")
    print("Run scripts/analyze_traces.py next to turn traces/*.jsonl into REPORT.md.")


if __name__ == "__main__":
    main()