#!/usr/bin/env python3
"""
scripts/run_experiment.py

The B5 experiment harness (PRD §9). Pins each arm to an explicit provider
and NEVER lets the router's `auto` mode decide — a rate-limit-triggered
fallback mid-run would silently contaminate the comparison. Runs requests
**interleaved** across arms (round-robin), not block-by-block, so
provider-side variance (e.g. a temporary slowdown) doesn't get attributed
to whichever arm happened to run during it.

Usage:
    python scripts/run_experiment.py \
        --crops-dir benchmark_canvases/ \
        --arms gemini,ollama \
        --requests-per-arm 45 \
        --backend http://localhost:8000

Each file in --crops-dir should be a .webp crop. If you don't have real
benchmark canvases yet, use --synthetic N to generate N solid-color
placeholder crops so you can exercise the harness end-to-end before your
Five Canvases are ready.
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
    img.save(buf, format="WEBP")
    return buf.getvalue()


def load_crops(crops_dir: Path | None, synthetic: int) -> list[bytes]:
    if synthetic:
        return [make_synthetic_crop(i) for i in range(synthetic)]
    if crops_dir is None:
        raise ValueError("Provide --crops-dir or --synthetic N")
    files = sorted(crops_dir.glob("*.webp"))
    if not files:
        raise FileNotFoundError(f"No .webp files found in {crops_dir}")
    return [f.read_bytes() for f in files]


def build_request_body(crop_bytes: bytes, arm: str) -> dict:
    return {
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
        "provider_override": arm,
    }


def run_one(client: httpx.Client, backend: str, crop_bytes: bytes, arm: str) -> dict:
    body = build_request_body(crop_bytes, arm)
    t0 = time.monotonic()
    created = client.post(f"{backend}/requests", json=body, timeout=30).json()
    request_id = created["request_id"]

    # Drain the SSE stream to completion (simplest correct client: block
    # until the "complete" or "error" event, or the connection closes).
    with client.stream("GET", f"{backend}/requests/{request_id}/stream", timeout=60) as resp:
        for line in resp.iter_lines():
            if line.startswith("event: complete") or line.startswith("event: error"):
                pass  # next line carries the data payload; we don't need it here

    t_render_ms = (time.monotonic() - t0) * 1000  # harness stands in for the client's render timer
    outcome = client.post(
        f"{backend}/requests/{request_id}/outcome",
        json={"outcome": "accepted", "t_render_ms": t_render_ms},
        timeout=30,
    ).json()
    return {"request_id": request_id, "arm": arm, "outcome": outcome}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crops-dir", type=Path, default=None)
    parser.add_argument("--synthetic", type=int, default=0, help="generate N placeholder crops instead")
    parser.add_argument("--arms", type=str, required=True, help="comma-separated, e.g. gemini,ollama")
    parser.add_argument("--requests-per-arm", type=int, default=45)
    parser.add_argument("--backend", type=str, default="http://localhost:8000")
    parser.add_argument(
        "--cooldown-s", type=float, default=0.0, help="pause between requests — see PRD §9 thermal note"
    )
    args = parser.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if len(arms) < 2:
        raise SystemExit("Need at least 2 arms (spec requires >=3 for the full protocol)")

    crops = load_crops(args.crops_dir, args.synthetic)

    # Build an interleaved schedule: round-robin across arms, not
    # block-by-block, per PRD §9.
    schedule: list[str] = []
    for _ in range(args.requests_per_arm):
        schedule.extend(arms)
    random.shuffle(arms)  # vary starting order per run, still round-robin within

    print(f"Running {len(schedule)} requests across {len(arms)} arms, interleaved.")
    results = []
    with httpx.Client() as client:
        for i, arm in enumerate(schedule):
            crop = crops[i % len(crops)]
            try:
                result = run_one(client, args.backend, crop, arm)
                results.append(result)
                print(f"[{i + 1}/{len(schedule)}] arm={arm} ok")
            except Exception as exc:  # noqa: BLE001 — log and keep going, don't let one failure kill the run
                print(f"[{i + 1}/{len(schedule)}] arm={arm} FAILED: {exc}")
            if args.cooldown_s:
                time.sleep(args.cooldown_s)

    print(f"Done. {len(results)}/{len(schedule)} requests completed successfully.")
    print("Run scripts/analyze_traces.py next to turn traces/*.jsonl into REPORT.md.")


if __name__ == "__main__":
    main()
