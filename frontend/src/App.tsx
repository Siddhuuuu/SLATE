import { useCallback, useState } from "react";
import type { Editor } from "tldraw";
import { Gauge, X } from "lucide-react";

import { Canvas } from "@/components/canvas/Canvas";
import { TopBar } from "@/components/layout/TopBar";
import { MetricsPanel } from "@/components/panel/MetricsPanel";

export default function App() {
  const [editor, setEditor] = useState<Editor | null>(null);
  const [generateNow, setGenerateNow] = useState<(() => void) | null>(null);
  const [metricsOpen, setMetricsOpen] = useState(false);

  const handleEditorReady = useCallback((ed: Editor) => setEditor(ed), []);
  const handleTriggerReady = useCallback((trigger: () => void) => setGenerateNow(() => trigger), []);

  return (
    <div className="flex h-screen w-screen flex-col bg-chrome">
      <TopBar editor={editor} onGenerateNow={generateNow ?? undefined} />

      <div className="relative flex-1">
        <Canvas onEditorReady={handleEditorReady} onTriggerReady={handleTriggerReady} />

        {/* Bottom-right, deliberately not top-right — tldraw's own native
            StylePanel (color/size/opacity) already lives top-right, and
            colliding with it was the actual bug. Collapsed by default so
            it never blocks the canvas; the toggle button is always
            visible regardless of open/closed state. */}
        <div className="pointer-events-none absolute bottom-4 right-4 z-10 flex flex-col items-end gap-2">
          {metricsOpen && (
            <div className="pointer-events-auto">
              <MetricsPanel />
            </div>
          )}
          <button
            onClick={() => setMetricsOpen((v) => !v)}
            className="pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full border border-border bg-chrome-2 text-muted-foreground shadow-lg transition-colors hover:text-foreground"
            title={metricsOpen ? "Hide session metrics" : "Show session metrics"}
          >
            {metricsOpen ? <X className="h-4 w-4" /> : <Gauge className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}