#!/usr/bin/env python3
"""
scripts/analyze_traces.py

Reads traces/*.jsonl, produces every table and chart that goes in
REPORT.md. Per PRD §9: this is the *only* path from raw traces to reported
numbers — if a figure is in the report, it traces back to this script, not
to hand-typing. Re-run it any time traces change; never edit REPORT.md's
numbers by hand.

Usage:
    python scripts/analyze_traces.py \
        --traces backend/traces/traces.jsonl \
        --out reports/

Produces:
    reports/summary.csv          per-arm (provider/tier) percentile table
    reports/latency_by_arm.png   p50/p90/p95/p99 bar chart per arm
    reports/cost_by_arm.png      cost per accepted draft, per arm
    reports/time_trend.png       latency over request order (thermal-throttle check, PRD §9)
    reports/REPORT.md            markdown report assembling the above
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_traces(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"No trace file at {path}. Run the app and generate some requests first."
        )
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            latency = rec.get("latency") or {}
            tokens = rec.get("tokens") or {}
            rows.append(
                {
                    "request_id": rec["request_id"],
                    "created_at": rec.get("created_at"),
                    "provider": rec.get("provider"),
                    "model": rec.get("model"),
                    "tier": rec.get("tier"),
                    "outcome": rec.get("outcome"),
                    "routing_reason": rec.get("routing_reason"),
                    "t_capture_ms": latency.get("t_capture_ms"),
                    "t_dispatch_ms": latency.get("t_dispatch_ms"),
                    "t_stream_ms": latency.get("t_stream_ms"),
                    "t_render_ms": latency.get("t_render_ms"),
                    "input_tokens": tokens.get("input_tokens"),
                    "output_tokens": tokens.get("output_tokens"),
                    "image_tokens": tokens.get("image_tokens"),
                    "cost_usd": rec.get("cost_usd"),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["t_total_ms"] = df[["t_capture_ms", "t_dispatch_ms", "t_stream_ms", "t_render_ms"]].sum(
        axis=1, min_count=1
    )
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df = df.sort_values("created_at").reset_index(drop=True)
    df["request_order"] = df.index
    return df


def percentile_table(df: pd.DataFrame, group_col: str = "provider") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for arm, g in df.groupby(group_col):
        latencies = g["t_total_ms"].dropna()
        if latencies.empty:
            continue
        rows.append(
            {
                group_col: arm,
                "n": len(g),
                "accept_rate": (g["outcome"] == "accepted").mean(),
                "p50_ms": np.percentile(latencies, 50),
                "p90_ms": np.percentile(latencies, 90),
                "p95_ms": np.percentile(latencies, 95),
                "p99_ms": np.percentile(latencies, 99) if len(latencies) >= 100 else np.nan,
                "max_ms": latencies.max(),
                "mean_cost_usd": g["cost_usd"].mean(),
                "total_cost_usd": g["cost_usd"].sum(),
            }
        )
    return pd.DataFrame(rows)


def plot_latency_by_arm(summary: pd.DataFrame, group_col: str, out_path: Path) -> None:
    if summary.empty:
        return
    metrics = ["p50_ms", "p90_ms", "p95_ms"]
    x = np.arange(len(summary))
    width = 0.25
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, m in enumerate(metrics):
        ax.bar(x + i * width, summary[m], width, label=m)
    ax.set_xticks(x + width)
    ax.set_xticklabels(summary[group_col])
    ax.set_ylabel("ms")
    ax.set_title("Latency percentiles by arm")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_cost_by_arm(summary: pd.DataFrame, group_col: str, out_path: Path) -> None:
    if summary.empty:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(summary[group_col], summary["mean_cost_usd"])
    ax.set_ylabel("USD per request")
    ax.set_title("Mean cost per request, by arm")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_time_trend(df: pd.DataFrame, out_path: Path) -> None:
    """Thermal-throttle / drift check per PRD §9 — flag if later requests
    in a run are systematically slower than earlier ones."""
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    for provider, g in df.groupby("provider"):
        ax.scatter(g["request_order"], g["t_total_ms"], s=10, label=provider, alpha=0.6)
    ax.set_xlabel("request order (chronological)")
    ax.set_ylabel("total latency (ms)")
    ax.set_title("Latency over request order — check for time-trend / throttling")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_report(summary: pd.DataFrame, df: pd.DataFrame, out_dir: Path) -> None:
    lines = ["# REPORT.md", "", f"_Generated by `scripts/analyze_traces.py` from {len(df)} traces._", ""]
    lines += ["## Per-arm summary", ""]
    if summary.empty:
        lines.append("_No traces yet — run some requests first._")
    else:
        lines.append(summary.to_markdown(index=False, floatfmt=".2f"))
    lines += ["", "## Charts", "", "![latency](latency_by_arm.png)", "", "![cost](cost_by_arm.png)", "", "![trend](time_trend.png)", ""]
    (out_dir / "REPORT.md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", type=Path, default=Path("backend/traces/traces.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("reports"))
    parser.add_argument("--group-by", choices=["provider", "tier"], default="provider")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    df = load_traces(args.traces)

    if df.empty:
        print(f"No traces found at {args.traces} — nothing to analyze yet.")
        return

    summary = percentile_table(df, group_col=args.group_by)
    summary.to_csv(args.out / "summary.csv", index=False)
    plot_latency_by_arm(summary, args.group_by, args.out / "latency_by_arm.png")
    plot_cost_by_arm(summary, args.group_by, args.out / "cost_by_arm.png")
    plot_time_trend(df, args.out / "time_trend.png")
    write_report(summary, df, args.out)

    print(f"Wrote {args.out}/summary.csv, latency_by_arm.png, cost_by_arm.png, time_trend.png, REPORT.md")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
