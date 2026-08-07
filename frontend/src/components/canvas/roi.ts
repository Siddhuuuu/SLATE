import { Box, exportToBlob, type Editor, type TLShapeId } from "tldraw";

import type { BoundingBox, RegionContext } from "@/lib/types";

export const DEFAULT_MARGIN_FRAC = 0.18; // 15-20% padding per PRD §6
export const DEFAULT_MAX_LONG_EDGE_PX = 1024; // caps payload + t_capture/t_dispatch
export const DEFAULT_IDLE_MS = 1000; // idle-trigger window, PRD §6 (~900-1200ms)

/** Reference area used to normalize ink_density into a friendly, roughly
 * 0-1-ish range for the router heuristic — an approximation, not a
 * calibrated physical unit. */
const DENSITY_REFERENCE_AREA_PX = 512 * 512;

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
 * Priority 2: a cluster of ink drawn recently, merged by a distance
 * threshold scaled by zoom. `recentDrawIds` comes from useRecentInk (below)
 * — shapes whose last change fell inside the idle window.
 */
export function inkClusterRoi(editor: Editor, recentDrawIds: TLShapeId[]): RoiSource | null {
  if (recentDrawIds.length === 0) return null;

  const boxes = recentDrawIds
    .map((id) => editor.getShapePageBounds(id))
    .filter((b): b is Box => Boolean(b));
  if (boxes.length === 0) return null;

  // Distance-threshold clustering scaled by zoom: merge any stroke bounds
  // that are within `clusterGapPx` (in screen px, converted to page units)
  // of the running union. For a v1 heuristic this is a single-pass union
  // rather than true nearest-neighbor clustering — good enough when the
  // idle window already limits the candidate set to "recent," which in
  // practice is almost always one coherent cluster.
  const zoom = editor.getZoomLevel();
  const clusterGapPagePx = 48 / zoom;

  let union = boxes[0].clone();
  for (const b of boxes.slice(1)) {
    const gap = boxDistance(union, b);
    if (gap <= clusterGapPagePx) {
      union = Box.Common([union, b]);
    }
  }

  return { bbox: union, source: "ink_cluster" };
}

/** Priority 3: fallback to whatever's currently on screen. */
export function viewportRoi(editor: Editor): RoiSource {
  return { bbox: editor.getViewportPageBounds(), source: "viewport" };
}

/** Runs the priority order from PRD §6 and returns the first hit. */
export function determineRoi(editor: Editor, recentDrawIds: TLShapeId[]): RoiSource {
  return selectionRoi(editor) ?? inkClusterRoi(editor, recentDrawIds) ?? viewportRoi(editor);
}

function boxDistance(a: Box, b: Box): number {
  const dx = Math.max(a.minX - b.maxX, b.minX - a.maxX, 0);
  const dy = Math.max(a.minY - b.maxY, b.minY - a.maxY, 0);
  return Math.hypot(dx, dy);
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
    format: "webp",
    opts: { background: true, bounds: padded, scale, padding: 0 },
  });

  const imageB64 = await blobToBase64(blob);
  const widthPx = Math.round(padded.width * scale);
  const heightPx = Math.round(padded.height * scale);

  const strokeCount = opts.strokeCount ?? 0;
  const area = Math.max(padded.width * padded.height, 1);
  const inkDensity = (strokeCount / area) * DENSITY_REFERENCE_AREA_PX;

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
