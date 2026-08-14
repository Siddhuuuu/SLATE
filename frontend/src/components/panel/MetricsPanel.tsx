import { useEffect, useState } from "react";
import { Activity, CircleDollarSign, Gauge, Layers, TrendingUp } from "lucide-react";

import { fetchMetricsSummary } from "@/lib/api";
import type { MetricsSummary } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const POLL_INTERVAL_MS = 1500; // "1-2s" per PRD §7.4 — cheap enough to never jank

function formatPct(x: number | null): string {
  if (x === null) return "—";
  return `${Math.round(x * 100)}%`;
}

function formatMs(x: number | null): string {
  if (x === null) return "—";
  return x < 1000 ? `${Math.round(x)}ms` : `${(x / 1000).toFixed(2)}s`;
}

function formatUsd(x: number | null): string {
  if (x === null) return "—";
  return x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(2)}`;
}

interface StatRowProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  tooltip?: string;
}

function StatRow({ icon, label, value, tooltip }: StatRowProps) {
  return (
    <div className="flex items-center justify-between py-1.5" title={tooltip}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <span className="font-mono text-sm tabular">{value}</span>
    </div>
  );
}

export function MetricsPanel() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await fetchMetricsSummary();
        if (!cancelled) {
          setSummary(data);
          setUnreachable(false);
        }
      } catch {
        if (!cancelled) setUnreachable(true);
      }
    }

    void poll();
    const interval = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <Card className="w-72 border-chrome-2 bg-chrome-2/60 shadow-none">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between">
          <span>Session metrics</span>
          <span
            className={cn("h-1.5 w-1.5 rounded-full", unreachable ? "bg-destructive" : "bg-ready")}
            title={unreachable ? "Backend unreachable" : "Live"}
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {unreachable && !summary ? (
          <p className="text-xs text-muted-foreground">
            Can't reach the backend at the configured URL — is it running?
          </p>
        ) : (
          <>
            <div className="divide-y divide-border/50">
              <StatRow
                icon={<Layers className="h-3.5 w-3.5" />}
                label="Requests"
                value={summary ? `${summary.total_requests}` : "…"}
              />
              <StatRow
                icon={<Activity className="h-3.5 w-3.5" />}
                label="In flight"
                value={summary ? `${summary.in_flight}` : "…"}
              />
              <StatRow
                icon={<Gauge className="h-3.5 w-3.5" />}
                label="Avg render"
                value={summary ? formatMs(summary.avg_render_ms) : "…"}
              />
              <StatRow
                icon={<CircleDollarSign className="h-3.5 w-3.5" />}
                label="Session cost"
                value={summary ? formatUsd(summary.total_cost_usd) : "…"}
              />
            </div>

            <Separator className="my-2" />

            {/* The four required KPIs (brief Section 5, B3) */}
            <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              <TrendingUp className="h-3 w-3" />
              KPIs
            </div>
            <div className="divide-y divide-border/50">
              <StatRow
                icon={<span className="w-3.5 text-center text-[10px] font-mono">$</span>}
                label="CPAD"
                tooltip="Cost per Accepted Draft — total spend / drafts accepted"
                value={summary ? formatUsd(summary.kpis.cpad_usd) : "…"}
              />
              <StatRow
                icon={<span className="w-3.5 text-center text-[10px] font-mono">%</span>}
                label="DAR"
                tooltip="Draft Acceptance Rate — accepted / (accepted + discarded)"
                value={summary ? formatPct(summary.kpis.dar) : "…"}
              />
              <StatRow
                icon={<span className="w-3.5 text-center text-[10px] font-mono">%</span>}
                label="WTR"
                tooltip="Wasted Token Ratio — tokens spent on discarded/cancelled/superseded/timeout/error requests, as a share of all tokens"
                value={summary ? formatPct(summary.kpis.wtr) : "…"}
              />
              <StatRow
                icon={<span className="w-3.5 text-center text-[10px] font-mono">%</span>}
                label={`BC (${summary ? summary.kpis.budget_ms : "…"}ms)`}
                tooltip="Budget Compliance — share of requests meeting the declared p95 e2e latency budget"
                value={summary ? formatPct(summary.kpis.bc) : "…"}
              />
            </div>

            {summary && (summary.superseded > 0 || summary.timeouts > 0 || summary.errors > 0) && (
              <>
                <Separator className="my-2" />
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                  {summary.superseded > 0 && <span>superseded: {summary.superseded}</span>}
                  {summary.timeouts > 0 && <span>timeouts: {summary.timeouts}</span>}
                  {summary.errors > 0 && <span>errors: {summary.errors}</span>}
                </div>
              </>
            )}
          </>
        )}
        <Separator className="my-2" />
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          Durable copy in <code className="font-mono">traces/traces.jsonl</code>. Run{" "}
          <code className="font-mono">scripts/analyze_traces.py</code> to turn it into REPORT.md.
        </p>
      </CardContent>
    </Card>
  );
}
