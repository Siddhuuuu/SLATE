import { Box, exportToBlob, type Editor, type TLShapeId } from "tldraw";

import type { BoundingBox, RegionContext } from "@/lib/types";

export const DEFAULT_MARGIN_FRAC = 0.18; // 15-20% padding per PRD §6
export const DEFAULT_MAX_LONG_EDGE_PX = 1024; // caps payload + t_capture/t_dispatch
export const DEFAULT_IDLE_MS = 1000; // idle-trigger window, PRD §6 (~900-1200ms)

/** Reference area used to normalize ink_density into a roughly 0-1-ish
 * range for the router heuristic. MAX_EXPECTED_STROKES_AT_REFERENCE is
 * the stroke count treated as "maximally dense" at that reference area —
 * without it, density scales linearly with raw stroke count and blows
 * past every threshold in router.py (0.15-0.45) for any real drawing.
 * Confirmed against a real trace: 7 strokes in a ~285,000px² region
 * produced density=6.46 under the old formula — 18x the fast-tier
 * threshold — for what was actually a simple, sparse region. This is a
 * one-sample recalibration, not a fitted constant; revisit once more
 * real trace data exists, per this file's own stated pattern. */
const DENSITY_REFERENCE_AREA_PX = 512 * 512;
const MAX_EXPECTED_STROKES_AT_REFERENCE = 30;

export interface RoiSource {
  bbox: Box;
  source: RegionContext["source"];
}

/** Priority 1: an explicit user selection, if one exists. */
export function selectionRoi(editor: Editor): RoiSource | null {
  const bounds = editor.getSelectionPageBounds();
  if (!bounds || bounds.width === 0 || bounds.height === 0) return null;
  return { bbox: bounds, source: "selection" };
}

/**
 * Priority 2: everything in `drawIds` unioned into one region — no
 * distance-threshold sub-clustering. An earlier version tried to merge
 * only strokes within ~48px of the running union, which silently DROPPED
 * any stroke further away than that instead of including it — writing
 * something like "E=mc²" with normal spacing between characters would
 * lose everything after the first gap. A full union of every id the
 * caller passes in is simpler and can't drop content; which ids are
 * "still relevant" is now the caller's job (see useDraftLifecycle.ts's
 * uncommitted-ink accumulator), not this function's.
 */
export function inkClusterRoi(editor: Editor, drawIds: TLShapeId[]): RoiSource | null {
  if (drawIds.length === 0) return null;

  const boxes = drawIds.map((id) => editor.getShapePageBounds(id)).filter((b): b is Box => Boolean(b));
  if (boxes.length === 0) return null;

  return { bbox: Box.Common(boxes), source: "ink_cluster" };
}

/** Priority 3: fallback to whatever's currently on screen. */
export function viewportRoi(editor: Editor): RoiSource {
  return { bbox: editor.getViewportPageBounds(), source: "viewport" };
}

/** Runs the priority order from PRD §6 and returns the first hit. */
export function determineRoi(editor: Editor, drawIds: TLShapeId[]): RoiSource {
  return selectionRoi(editor) ?? inkClusterRoi(editor, drawIds) ?? viewportRoi(editor);
}

/** Pads a page-space box by a fraction of its own size (min 15-20%, PRD §6). */
export function padBox(box: Box, marginFrac = DEFAULT_MARGIN_FRAC): Box {
  const padX = box.width * marginFrac;
  const padY = box.height * marginFrac;
  return new Box(box.x - padX, box.y - padY, box.width + padX * 2, box.height + padY * 2);
}

export interface CapturedRegion {
  imageB64: string;
  widthPx: number;
  heightPx: number;
  context: RegionContext;
}

/**
 * Renders `bbox` (page space) to a WebP crop capped at `maxLongEdge`,
 * and assembles the non-image context PRD §6 asks for alongside it.
 */
export async function captureRegion(
  editor: Editor,
  roi: RoiSource,
  opts: {
    marginFrac?: number;
    maxLongEdge?: number;
    strokeCount?: number;
    nearbyShapeTypes?: string[];
    nearbyAcceptedDraftIds?: string[];
  } = {}
): Promise<CapturedRegion> {
  const padded = padBox(roi.bbox, opts.marginFrac ?? DEFAULT_MARGIN_FRAC);

  const longEdgePageUnits = Math.max(padded.width, padded.height);
  const maxLongEdge = opts.maxLongEdge ?? DEFAULT_MAX_LONG_EDGE_PX;
  const scale = Math.min(1, maxLongEdge / Math.max(longEdgePageUnits, 1));

  const shapeIds = [...editor.getCurrentPageShapeIds()];

  const blob = await exportToBlob({
    editor,
    ids: shapeIds,
    format: "png", // WebP isn't decodable by Ollama's Go image backend — see backend README notes
    opts: { background: true, bounds: padded, scale, padding: 0 },
  });

  const imageB64 = await blobToBase64(blob);
  const widthPx = Math.round(padded.width * scale);
  const heightPx = Math.round(padded.height * scale);

  const strokeCount = opts.strokeCount ?? 0;
  const area = Math.max(padded.width * padded.height, 1);
  const inkDensity = (strokeCount / area) * DENSITY_REFERENCE_AREA_PX / MAX_EXPECTED_STROKES_AT_REFERENCE;

  const bbox: BoundingBox = { x: padded.x, y: padded.y, width: padded.width, height: padded.height };

  return {
    imageB64,
    widthPx,
    heightPx,
    context: {
      bbox,
      zoom: editor.getZoomLevel(),
      source: roi.source,
      nearby_shape_types: opts.nearbyShapeTypes ?? [],
      nearby_accepted_draft_ids: opts.nearbyAcceptedDraftIds ?? [],
      stroke_count: strokeCount,
      ink_density: inkDensity,
    },
  };
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // strip the "data:*/*;base64," prefix — backend expects raw base64
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
