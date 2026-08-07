import { useEffect, useState } from "react";
import { Tldraw, type Editor } from "tldraw";
import "tldraw/tldraw.css";

import { DraftShapeUtil, DRAFT_SHAPE_TYPE } from "./DraftShapeUtil";
import { useDraftLifecycle } from "@/hooks/useDraftLifecycle";

const shapeUtils = [DraftShapeUtil];

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
        onMount={(ed) => {
          setEditor(ed);
          onEditorReady?.(ed);
        }}
      />
    </div>
  );
}
