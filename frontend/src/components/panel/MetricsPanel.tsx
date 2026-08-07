import { useEffect, useState } from "react";
import { Activity, CircleDollarSign, Gauge, Layers } from "lucide-react";

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

function formatUsd(x: number): string {
  return x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(2)}`;
}

interface StatRowProps {
  icon: React.ReactNode;
  label: string;
  value: string;
}

function StatRow({ icon, label, value }: StatRowProps) {
  return (
    <div className="flex items-center justify-between py-1.5">
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
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              unreachable ? "bg-destructive" : "bg-ready"
            )}
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
              label="Acceptance rate"
              value={summary ? formatPct(summary.draft_acceptance_rate) : "…"}
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
