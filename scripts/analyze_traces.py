#!/usr/bin/env python3
"""
scripts/analyze_traces.py

Reads traces/*.jsonl, produces every table and chart that goes in
REPORT.md. This is the *only* path from raw traces to reported numbers —
if a figure is in the report, it traces back to this script, not to
hand-typing. Re-run it any time traces change; never edit REPORT.md's
numbers by hand.

Groups by config_id (the brief's own arm identifier, set by
run_experiment.py) by default — falls back to provider if config_id
wasn't set on older traces.

Usage:
    python scripts/analyze_traces.py \
        --traces backend/traces/traces.jsonl \
        --out reports/

Produces:
    reports/summary.csv          per-arm p50/p95 e2e, mean tokens, mean cost, DAR
    reports/latency_by_arm.png   p50/p95 e2e bar chart per arm
    reports/cost_by_arm.png      cost per accepted draft, per arm
    reports/time_trend.png       latency over request order (thermal-throttle check)
    reports/REPORT.md            markdown report assembling the above + KPIs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from kpis import compute_all_kpis, DEFAULT_LATENCY_BUDGET_MS  # noqa: E402


def load_traces(path: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Returns both a flattened DataFrame (for percentile/plotting work)
    and the raw list of trace dicts (for kpis.py, which expects the
    brief's nested trace shape directly, not a flattened one)."""
    if not path.exists():
        raise FileNotFoundError(
            f"No trace file at {path}. Run the app and generate some requests first."
        )
    raw: list[dict] = []
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            raw.append(rec)
            latency = rec.get("latency") or {}
            tokens = rec.get("tokens") or {}
            rows.append(
                {
                    "request_id": rec["request_id"],
                    "created_at": rec.get("created_at"),
                    "provider": rec.get("provider"),
                    "model": rec.get("model"),
                    "tier": rec.get("tier"),
                    "config_id": rec.get("config_id") or rec.get("provider"),
                    "trigger": rec.get("trigger"),
                    "outcome": rec.get("outcome"),
                    "routing_reason": rec.get("routing_reason"),
                    "t_capture_ms": latency.get("t_capture_ms"),
                    "t_dispatch_ms": latency.get("t_dispatch_ms"),
                    "ttfb_ms": latency.get("ttfb_ms"),
                    "ttft_ms": latency.get("ttft_ms"),
                    "t_stream_ms": latency.get("t_stream_ms"),
                    "t_render_ms": latency.get("t_render_ms"),
                    "e2e_ms": latency.get("e2e_ms"),
                    "input_text_tokens": tokens.get("input_text_tokens"),
                    "input_image_tokens": tokens.get("input_image_tokens"),
                    "output_tokens": tokens.get("output_tokens"),
                    "reasoning_tokens": tokens.get("reasoning_tokens"),
                    "total_tokens": tokens.get("total_tokens"),
                    "cost_usd": rec.get("cost_usd"),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df, raw
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df = df.sort_values("created_at").reset_index(drop=True)
    df["request_order"] = df.index
    return df, raw


def percentile_table(df: pd.DataFrame, group_col: str = "config_id") -> pd.DataFrame:
    """p50/p95 e2e (the brief's own required statistic), mean tokens,
    mean cost, and DAR per arm."""
    if df.empty:
        return pd.DataFrame()
    rows = []
    for arm, g in df.groupby(group_col):
        e2e = g["e2e_ms"].dropna()
        accepted = (g["outcome"] == "accepted").sum()
        discarded = (g["outcome"] == "discarded").sum()
        returned = accepted + discarded
        rows.append(
            {
                group_col: arm,
                "n": len(g),
                "n_with_e2e": len(e2e),
                "dar": (accepted / returned) if returned else None,
                "p50_e2e_ms": np.percentile(e2e, 50) if len(e2e) else np.nan,
                "p95_e2e_ms": np.percentile(e2e, 95) if len(e2e) else np.nan,
                "max_e2e_ms": e2e.max() if len(e2e) else np.nan,
                "mean_total_tokens": g["total_tokens"].mean(),
                "mean_cost_usd": g["cost_usd"].mean(),
                "total_cost_usd": g["cost_usd"].sum(),
            }
        )
    return pd.DataFrame(rows)


def plot_latency_by_arm(summary: pd.DataFrame, group_col: str, out_path: Path) -> None:
    if summary.empty:
        return
    metrics = ["p50_e2e_ms", "p95_e2e_ms"]
    x = np.arange(len(summary))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, m in enumerate(metrics):
        ax.bar(x + i * width, summary[m], width, label=m)
    ax.set_xticks(x + width / 2)
    ax.set_xticklabels(summary[group_col], rotation=20, ha="right")
    ax.set_ylabel("ms")
    ax.set_title("e2e latency (p50 / p95) by arm")
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
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_time_trend(df: pd.DataFrame, group_col: str, out_path: Path) -> None:
    """Thermal-throttle / drift check — flag if later requests in a run
    are systematically slower than earlier ones."""
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    for arm, g in df.groupby(group_col):
        ax.scatter(g["request_order"], g["e2e_ms"], s=10, label=arm, alpha=0.6)
    ax.set_xlabel("request order (chronological)")
    ax.set_ylabel("e2e latency (ms)")
    ax.set_title("Latency over request order — check for time-trend / throttling")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_report(summary: pd.DataFrame, df: pd.DataFrame, raw: list[dict], out_dir: Path) -> None:
    kpis = compute_all_kpis(raw, budget_ms=DEFAULT_LATENCY_BUDGET_MS)
    k = kpis.as_dict()

    lines = [
        "# REPORT.md",
        "",
        f"_Generated by `scripts/analyze_traces.py` from {len(df)} traces. "
        f"Every number below traces back to this script — none are hand-typed._",
        "",
        "## Session-wide KPIs",
        "",
        "| KPI | Value | Definition |",
        "|---|---|---|",
        f"| CPAD | {'$' + format(k['cpad_usd'], '.4f') if k['cpad_usd'] is not None else '—'} | Cost per Accepted Draft |",
        f"| DAR | {format(k['dar'] * 100, '.1f') + '%' if k['dar'] is not None else '—'} | Draft Acceptance Rate |",
        f"| WTR | {format(k['wtr'] * 100, '.1f') + '%' if k['wtr'] is not None else '—'} | Wasted Token Ratio |",
        f"| BC | {format(k['bc'] * 100, '.1f') + '%' if k['bc'] is not None else '—'} | Budget Compliance (p95 e2e ≤ {k['budget_ms']}ms) |",
        "",
        "## Per-arm summary (grouped by config_id)",
        "",
    ]
    if summary.empty:
        lines.append("_No traces yet — run some requests first._")
    else:
        lines.append(summary.to_markdown(index=False, floatfmt=".3f"))

    lines += [
        "",
        "## Charts",
        "",
        "![latency](latency_by_arm.png)",
        "",
        "![cost](cost_by_arm.png)",
        "",
        "![trend](time_trend.png)",
        "",
        "## Protocol",
        "",
        "_Fill in: which variable was tested, the five benchmark canvases used, "
        "arm definitions, repetitions per arm, and whether arm order was interleaved._",
        "",
        "## Optimizations (before/after)",
        "",
        "_Fill in: the two optimizations implemented, and the measured p50/p95/cost "
        "delta for each, run through this same script before and after._",
        "",
        "## Recommendation",
        "",
        "_Fill in: the trade-off, stated plainly, given the numbers above._",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", type=Path, default=Path("backend/traces/traces.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("reports"))
    parser.add_argument("--group-by", choices=["config_id", "provider", "tier"], default="config_id")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    df, raw = load_traces(args.traces)

    if df.empty:
        print(f"No traces found at {args.traces} — nothing to analyze yet.")
        return

    summary = percentile_table(df, group_col=args.group_by)
    summary.to_csv(args.out / "summary.csv", index=False)
    plot_latency_by_arm(summary, args.group_by, args.out / "latency_by_arm.png")
    plot_cost_by_arm(summary, args.group_by, args.out / "cost_by_arm.png")
    plot_time_trend(df, args.group_by, args.out / "time_trend.png")
    write_report(summary, df, raw, args.out)

    print(f"Wrote {args.out}/summary.csv, latency_by_arm.png, cost_by_arm.png, time_trend.png, REPORT.md")
    print(summary.to_string(index=False))
    print()
    print("Session KPIs:", compute_all_kpis(raw, budget_ms=DEFAULT_LATENCY_BUDGET_MS).as_dict())


if __name__ == "__main__":
    main()
