import { useEffect, useState } from "react";
import { Tldraw, type Editor, type TLComponents } from "tldraw";
import "tldraw/tldraw.css";
import "katex/dist/katex.min.css";

import { DraftShapeUtil, DRAFT_SHAPE_TYPE } from "./DraftShapeUtil";
import { useDraftLifecycle } from "@/hooks/useDraftLifecycle";

const shapeUtils = [DraftShapeUtil];

// DebugMenu/DebugPanel are tldraw's own dev-testing chrome (the "..." menu
// with "Show toast" / "Create 100 shapes" / etc.) — never meant to ship in
// a real product. tldraw's native StylePanel (the color/opacity/size
// picker) is left alone; that's real drawing functionality the app needs.
const components: TLComponents = {
  DebugMenu: null,
  DebugPanel: null,
};

export interface CanvasProps {
  onEditorReady?: (editor: Editor) => void;
  onTriggerReady?: (trigger: () => void) => void;
}

/**
 * Filters draft shapes out of a shape-id list — the enforcement point for
 * PRD A5's "drafts never appear in save/export." Confirmed content and
 * in-progress drafts already live in the same tldraw store (kept simple
 * on purpose, PRD §5), so this filter is what keeps them from leaking into
 * exports rather than a separate namespace/store.
 */
export function excludeDrafts(editor: Editor, ids: Iterable<string>): string[] {
  return [...ids].filter((id) => editor.getShape(id as any)?.type !== DRAFT_SHAPE_TYPE) as string[];
}

export function Canvas({ onEditorReady, onTriggerReady }: CanvasProps) {
  const [editor, setEditor] = useState<Editor | null>(null);

  const { triggerManualCapture } = useDraftLifecycle(editor);

  useEffect(() => {
    onTriggerReady?.(triggerManualCapture);
  }, [triggerManualCapture, onTriggerReady]);

  return (
    <div className="h-full w-full bg-paper">
      <Tldraw
        shapeUtils={shapeUtils}
        components={components}
        onMount={(ed) => {
          setEditor(ed);
          onEditorReady?.(ed);
        }}
      />
    </div>
  );
}