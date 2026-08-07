import { useCallback, useState } from "react";
import type { Editor } from "tldraw";

import { Canvas } from "@/components/canvas/Canvas";
import { TopBar } from "@/components/layout/TopBar";
import { MetricsPanel } from "@/components/panel/MetricsPanel";

export default function App() {
  const [editor, setEditor] = useState<Editor | null>(null);
  const [generateNow, setGenerateNow] = useState<(() => void) | null>(null);

  const handleEditorReady = useCallback((ed: Editor) => setEditor(ed), []);
  const handleTriggerReady = useCallback((trigger: () => void) => setGenerateNow(() => trigger), []);

  return (
    <div className="flex h-screen w-screen flex-col bg-chrome">
      <TopBar editor={editor} onGenerateNow={generateNow ?? undefined} />

      <div className="relative flex-1">
        <Canvas onEditorReady={handleEditorReady} onTriggerReady={handleTriggerReady} />

        <div className="pointer-events-none absolute right-4 top-4 z-10">
          <div className="pointer-events-auto">
            <MetricsPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
