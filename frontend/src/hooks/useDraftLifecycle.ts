import { useCallback, useEffect, useRef } from "react";
import { createShapeId, type Editor, type TLShapeId } from "tldraw";

import { DRAFT_SHAPE_TYPE, registerDraftShapeCallbacks } from "@/components/canvas/DraftShapeUtil";
import { captureRegion, determineRoi, DEFAULT_IDLE_MS } from "@/components/canvas/roi";
import { cancelRequest, createRequest, reportOutcome, streamDraft } from "@/lib/api";
import type { Trigger } from "@/lib/types";

interface ActiveDraft {
  requestId: string;
  draftShapeId: TLShapeId;
  // null once the stream has completed (status "ready") — nothing left to
  // cancel client-side at that point, but the draft is still *unsettled*
  // (not yet accepted/discarded) and must still be superseded, not left
  // sitting next to a fresher capture.
  eventSource: EventSource | null;
  streamStartedAt: number;
  triggerFiredAt: number; // for e2e_ms — see finalize/markReady below
}

/** requestId -> { renderMs, e2eMs }, held until the user accepts/discards
 * and we can finally send both in POST /requests/{id}/outcome (PRD §7.1
 * clock-skew rule: these are measured client-side and sent as durations,
 * never as timestamps). */
interface PendingTiming {
  renderMs: number;
  e2eMs: number;
}
type PendingTimings = Map<string, PendingTiming>;

export function useDraftLifecycle(editor: Editor | null) {
  // Every draw-shape id created/updated since the LAST accept/discard.
  // Deliberately not time-windowed: "E=mc²" written with normal pauses
  // between characters is one uncommitted thought, not several. This set
  // only shrinks when finalizeOutcome() resets it.
  const uncommittedDrawIds = useRef<Set<TLShapeId>>(new Set());
  const idleTimer = useRef<number | null>(null);
  const activeDraft = useRef<ActiveDraft | null>(null);
  const pendingTimings = useRef<PendingTimings>(new Map());
  // Holds the current effect's triggerCapture so the stable callback below
  // can always reach the latest closure without itself changing identity.
  const triggerCaptureRef = useRef<(trigger: Trigger) => void>(() => {});

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

    function markReady(draftShapeId: TLShapeId, requestId: string, streamStartedAt: number, triggerFiredAt: number) {
      const now = performance.now();
      pendingTimings.current.set(requestId, {
        renderMs: now - streamStartedAt,
        e2eMs: now - triggerFiredAt, // brief's e2e: trigger fires -> draft visible, measured directly
      });
      const shape = editor!.getShape(draftShapeId);
      if (!shape) return;
      editor!.updateShape({ id: draftShapeId, type: DRAFT_SHAPE_TYPE, props: { status: "ready" } });
      // Still unsettled — just no longer has a live stream to cancel. Stays
      // in activeDraft so a later capture (more ink added) supersedes it
      // instead of spawning a second box next to it.
      if (activeDraft.current?.requestId === requestId) {
        activeDraft.current.eventSource = null;
      }
    }

    function markError(draftShapeId: TLShapeId, message: string) {
      const shape = editor!.getShape(draftShapeId);
      if (!shape) return;
      editor!.updateShape({
        id: draftShapeId,
        type: DRAFT_SHAPE_TYPE,
        props: { status: "error", text: `Couldn't generate a draft: ${message}` },
      });
      activeDraft.current = null;
    }

    async function finalizeOutcome(requestId: string, outcome: "accepted" | "discarded") {
      const shape = findDraftShapeByRequestId(requestId);
      const timing = pendingTimings.current.get(requestId);
      pendingTimings.current.delete(requestId);

      if (shape) {
        editor!.updateShape({ id: shape.id, type: DRAFT_SHAPE_TYPE, props: { status: outcome } });
        // Discarded drafts disappear; accepted ones stay as a settled
        // (solid-border) object on the canvas per the state machine in
        // PRD §5 — only discard actually removes the shape.
        if (outcome === "discarded") {
          window.setTimeout(() => editor!.deleteShape(shape.id), 150);
        }
      }

      if (activeDraft.current?.requestId === requestId) activeDraft.current = null;
      // This ink is now settled either way — the NEXT stroke starts a
      // brand new uncommitted region, not a continuation of this one.
      uncommittedDrawIds.current.clear();

      await reportOutcome(requestId, {
        outcome,
        t_render_ms: timing?.renderMs,
        e2e_ms: timing?.e2eMs,
      });
    }

    /** Replaces whatever draft is currently unsettled — streaming or
     * already ready — with nothing, clearing the way for a fresh capture
     * that reflects everything accumulated so far. Returns true if there
     * was something to supersede, which the caller uses to classify this
     * new request's trigger as "refine" rather than idle_pause/explicit. */
    async function supersedeActive(): Promise<boolean> {
      const current = activeDraft.current;
      if (!current) return false;
      current.eventSource?.close();
      await cancelRequest(current.requestId); // best-effort no-op if already finalized server-side
      const shape = editor!.getShape(current.draftShapeId);
      if (shape) editor!.deleteShape(shape.id);
      activeDraft.current = null;
      return true;
    }

    function scheduleIdleCheck() {
      if (idleTimer.current !== null) window.clearTimeout(idleTimer.current);
      idleTimer.current = window.setTimeout(() => {
        void triggerCapture("idle_pause");
      }, DEFAULT_IDLE_MS);
    }

    async function triggerCapture(requestedTrigger: Trigger) {
      const triggerFiredAt = performance.now(); // e2e stopwatch starts here, per the brief's own definition

      const drawIds = [...uncommittedDrawIds.current];

      if (drawIds.length === 0 && editor!.getSelectedShapeIds().length === 0) {
        return; // nothing to react to — don't fire a request over an empty canvas
      }

      const t0 = performance.now();
      const roi = determineRoi(editor!, drawIds);
      const captured = await captureRegion(editor!, roi, { strokeCount: drawIds.length });
      const tCaptureMs = performance.now() - t0;

      const wasSuperseding = await supersedeActive();
      // "refine" per models.py's Trigger enum: a capture that replaced an
      // already-unsettled draft for the same evolving region, regardless
      // of whether idle timer or the explicit button fired it.
      const trigger: Trigger = wasSuperseding ? "refine" : requestedTrigger;

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
          trigger,
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
        onComplete: () => markReady(draftShapeId, created.request_id, streamStartedAt, triggerFiredAt),
        onError: (message) => markError(draftShapeId, message),
      });

      activeDraft.current = {
        requestId: created.request_id,
        draftShapeId,
        eventSource,
        streamStartedAt,
        triggerFiredAt,
      };
    }

    registerDraftShapeCallbacks({
      onAccept: (requestId) => void finalizeOutcome(requestId, "accepted"),
      onDiscard: (requestId) => void finalizeOutcome(requestId, "discarded"),
    });

    triggerCaptureRef.current = (trigger: Trigger) => void triggerCapture(trigger);

    // Track ink activity: any create/update of a `draw`-type shape adds it
    // to the uncommitted set (permanently, until accept/discard) and resets
    // the idle timer. Per PRD §6, the trigger is idle-since-last-pointer-up
    // OR an explicit gesture — the explicit-gesture path is wired in
    // TopBar's "Generate now" button, which calls triggerCapture directly.
    const unlisten = editor.store.listen(
      (entry) => {
        let sawInk = false;
        for (const record of Object.values(entry.changes.added)) {
          if ((record as any).typeName === "shape" && (record as any).type === "draw") {
            uncommittedDrawIds.current.add((record as any).id);
            sawInk = true;
          }
        }
        for (const [, next] of Object.values(entry.changes.updated) as any[]) {
          if (next.typeName === "shape" && next.type === "draw") {
            uncommittedDrawIds.current.add(next.id);
            sawInk = true;
          }
        }
        if (sawInk) scheduleIdleCheck();
      },
      { source: "user", scope: "document" }
    );

    // Keyboard: Enter accepts, Escape discards the current READY draft —
    // "every frequent action has a shortcut, and they are discoverable"
    // (see the visible Enter/Esc hints next to the buttons themselves in
    // DraftShapeUtil.tsx). Guarded so it never hijacks Enter/Escape when
    // there's no ready draft to act on, or while typing in a text field.
    function handleKeydown(e: KeyboardEvent) {
      const current = activeDraft.current;
      if (!current) return;
      const shape = editor!.getShape(current.draftShapeId);
      if (!shape || (shape.props as any).status !== "ready") return;

      const target = e.target as HTMLElement | null;
      const isTyping = target && ["INPUT", "TEXTAREA"].includes(target.tagName);
      if (isTyping) return;

      if (e.key === "Enter") {
        e.preventDefault();
        void finalizeOutcome(current.requestId, "accepted");
      } else if (e.key === "Escape") {
        e.preventDefault();
        void finalizeOutcome(current.requestId, "discarded");
      }
    }
    window.addEventListener("keydown", handleKeydown);

    return () => {
      unlisten();
      window.removeEventListener("keydown", handleKeydown);
      if (idleTimer.current !== null) window.clearTimeout(idleTimer.current);
      activeDraft.current?.eventSource?.close();
    };
  }, [editor]);

  /** Explicit-gesture trigger (PRD §6) — wired to TopBar's "Generate now"
   * button. Fires the same capture path as the idle timer, immediately. */
  const triggerManualCapture = useCallback(() => {
    triggerCaptureRef.current("explicit");
  }, []);

  return { triggerManualCapture };
}
