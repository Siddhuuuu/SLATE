import { useCallback, useEffect, useRef } from "react";
import { createShapeId, type Editor, type TLShapeId } from "tldraw";

import { DRAFT_SHAPE_TYPE, registerDraftShapeCallbacks } from "@/components/canvas/DraftShapeUtil";
import { captureRegion, determineRoi, DEFAULT_IDLE_MS } from "@/components/canvas/roi";
import { cancelRequest, createRequest, reportOutcome, streamDraft } from "@/lib/api";

interface InFlight {
  requestId: string;
  draftShapeId: TLShapeId;
  eventSource: EventSource;
  streamStartedAt: number;
}

/** requestId -> render duration, held until the user accepts/discards and
 * we can finally send it in POST /requests/{id}/outcome (PRD §7.1). */
type PendingRenderTimes = Map<string, number>;

export function useDraftLifecycle(editor: Editor | null) {
  const recentDrawTimestamps = useRef<Map<TLShapeId, number>>(new Map());
  const idleTimer = useRef<number | null>(null);
  const inFlight = useRef<InFlight | null>(null);
  const pendingRenderTimes = useRef<PendingRenderTimes>(new Map());
  // Holds the current effect's triggerCapture so the stable callback below
  // can always reach the latest closure without itself changing identity.
  const triggerCaptureRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!editor) return;

    function findDraftShapeByRequestId(requestId: string) {
      return editor!
        .getCurrentPageShapes()
        .find((s) => s.type === DRAFT_SHAPE_TYPE && (s.props as any).requestId === requestId);
    }

    function appendToken(draftShapeId: TLShapeId, token: string) {
      const shape = editor!.getShape(draftShapeId);
      if (!shape) return;
      const prevText = (shape.props as any).text as string;
      editor!.updateShape({
        id: draftShapeId,
        type: DRAFT_SHAPE_TYPE,
        props: { text: prevText + token },
      });
    }

    function markReady(draftShapeId: TLShapeId, requestId: string, streamStartedAt: number) {
      const renderMs = performance.now() - streamStartedAt;
      pendingRenderTimes.current.set(requestId, renderMs);
      const shape = editor!.getShape(draftShapeId);
      if (!shape) return;
      editor!.updateShape({ id: draftShapeId, type: DRAFT_SHAPE_TYPE, props: { status: "ready" } });
      if (inFlight.current?.requestId === requestId) inFlight.current = null;
    }

    function markError(draftShapeId: TLShapeId, message: string) {
      const shape = editor!.getShape(draftShapeId);
      if (!shape) return;
      editor!.updateShape({
        id: draftShapeId,
        type: DRAFT_SHAPE_TYPE,
        props: { status: "error", text: `Couldn't generate a draft: ${message}` },
      });
      inFlight.current = null;
    }

    async function finalizeOutcome(requestId: string, outcome: "accepted" | "discarded") {
      const shape = findDraftShapeByRequestId(requestId);
      const renderMs = pendingRenderTimes.current.get(requestId);
      pendingRenderTimes.current.delete(requestId);

      if (shape) {
        editor!.updateShape({ id: shape.id, type: DRAFT_SHAPE_TYPE, props: { status: outcome } });
        // Discarded drafts disappear; accepted ones stay as a settled
        // (solid-border) object on the canvas per the state machine in
        // PRD §5 — only discard actually removes the shape.
        if (outcome === "discarded") {
          window.setTimeout(() => editor!.deleteShape(shape.id), 150);
        }
      }

      await reportOutcome(requestId, { outcome, t_render_ms: renderMs });
    }

    async function supersedeInFlight() {
      const current = inFlight.current;
      if (!current) return;
      current.eventSource.close();
      await cancelRequest(current.requestId);
      const shape = editor!.getShape(current.draftShapeId);
      if (shape) editor!.deleteShape(shape.id);
      inFlight.current = null;
    }

    function scheduleIdleCheck() {
      if (idleTimer.current !== null) window.clearTimeout(idleTimer.current);
      idleTimer.current = window.setTimeout(() => {
        void triggerCapture();
      }, DEFAULT_IDLE_MS);
    }

    async function triggerCapture() {
      const now = Date.now();
      const recentIds = [...recentDrawTimestamps.current.entries()]
        .filter(([, t]) => now - t <= DEFAULT_IDLE_MS * 1.5)
        .map(([id]) => id);

      if (recentIds.length === 0 && editor!.getSelectedShapeIds().length === 0) {
        return; // nothing to react to — don't fire a request over an empty canvas
      }

      const t0 = performance.now();
      const roi = determineRoi(editor!, recentIds);
      const captured = await captureRegion(editor!, roi, { strokeCount: recentIds.length });
      const tCaptureMs = performance.now() - t0;

      await supersedeInFlight();

      const draftShapeId = createShapeId();
      editor!.createShape({
        id: draftShapeId,
        type: DRAFT_SHAPE_TYPE,
        x: captured.context.bbox.x,
        y: captured.context.bbox.y + captured.context.bbox.height + 16,
        props: {
          w: 280,
          h: 140,
          status: "pending",
          text: "",
          provider: "",
          tier: "",
          requestId: "",
        },
      });

      let created;
      try {
        created = await createRequest({
          image_b64: captured.imageB64,
          image_width_px: captured.widthPx,
          image_height_px: captured.heightPx,
          context: captured.context,
          t_capture_ms: tCaptureMs,
        });
      } catch (err) {
        markError(draftShapeId, err instanceof Error ? err.message : String(err));
        return;
      }

      editor!.updateShape({
        id: draftShapeId,
        type: DRAFT_SHAPE_TYPE,
        props: {
          requestId: created.request_id,
          provider: created.provider,
          tier: created.tier,
          status: "streaming",
        },
      });

      const streamStartedAt = performance.now();
      const eventSource = streamDraft(created.request_id, {
        onToken: (text) => appendToken(draftShapeId, text),
        onComplete: () => markReady(draftShapeId, created.request_id, streamStartedAt),
        onError: (message) => markError(draftShapeId, message),
      });

      inFlight.current = { requestId: created.request_id, draftShapeId, eventSource, streamStartedAt };
    }

    registerDraftShapeCallbacks({
      onAccept: (requestId) => void finalizeOutcome(requestId, "accepted"),
      onDiscard: (requestId) => void finalizeOutcome(requestId, "discarded"),
    });

    triggerCaptureRef.current = () => void triggerCapture();

    // Track ink activity: any create/update of a `draw`-type shape resets
    // the idle timer. Per PRD §6, the trigger is idle-since-last-pointer-up
    // OR an explicit gesture — the explicit-gesture path is wired in
    // TopBar's "Generate now" button, which calls triggerCapture directly.
    const unlisten = editor.store.listen(
      (entry) => {
        let sawInk = false;
        for (const record of Object.values(entry.changes.added)) {
          if ((record as any).typeName === "shape" && (record as any).type === "draw") {
            recentDrawTimestamps.current.set((record as any).id, Date.now());
            sawInk = true;
          }
        }
        for (const [, next] of Object.values(entry.changes.updated) as any[]) {
          if (next.typeName === "shape" && next.type === "draw") {
            recentDrawTimestamps.current.set(next.id, Date.now());
            sawInk = true;
          }
        }
        if (sawInk) scheduleIdleCheck();
      },
      { source: "user", scope: "document" }
    );

    return () => {
      unlisten();
      if (idleTimer.current !== null) window.clearTimeout(idleTimer.current);
      inFlight.current?.eventSource.close();
    };
  }, [editor]);

  /** Explicit-gesture trigger (PRD §6) — wired to TopBar's "Generate now"
   * button. Fires the same capture path as the idle timer, immediately. */
  const triggerManualCapture = useCallback(() => {
    triggerCaptureRef.current();
  }, []);

  return { triggerManualCapture };
}
