import { exportToBlob, getSnapshot, loadSnapshot, type Editor } from "tldraw";

import { excludeDrafts } from "./Canvas";

const SNAPSHOT_FORMAT_VERSION = 1;

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Downloads the current canvas as a JSON file. Draft shapes are stripped
 * before serializing — accepted drafts have already had their `status`
 * flipped to a settled state and stay; anything still pending/streaming/
 * discarded does not belong in a saved file. See PRD §5 (A5).
 */
export function saveSnapshotToFile(editor: Editor, filename = "slate-canvas.json") {
  const snapshot = getSnapshot(editor.store);
  const doc = snapshot.document as any;

  const filteredStore = Object.fromEntries(
    Object.entries(doc.store).filter(([, record]: [string, any]) => record.type !== "draft")
  );

  const payload = {
    format_version: SNAPSHOT_FORMAT_VERSION,
    saved_at: new Date().toISOString(),
    document: { ...doc, store: filteredStore },
    session: snapshot.session,
  };

  downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }), filename);
}

export async function loadSnapshotFromFile(editor: Editor, file: File): Promise<void> {
  const text = await file.text();
  const parsed = JSON.parse(text);
  if (parsed.format_version !== SNAPSHOT_FORMAT_VERSION) {
    throw new Error(
      `Unrecognized snapshot format_version ${parsed.format_version} (expected ${SNAPSHOT_FORMAT_VERSION})`
    );
  }
  loadSnapshot(editor.store, { document: parsed.document, session: parsed.session });
}

/** PNG export, confirmed content only — drafts excluded via excludeDrafts(). */
export async function exportConfirmedPng(editor: Editor, filename = "slate-canvas.png") {
  const allIds = editor.getCurrentPageShapeIds();
  const confirmedIds = excludeDrafts(editor, allIds);
  if (confirmedIds.length === 0) return;

  const blob = await exportToBlob({
    editor,
    ids: confirmedIds as any,
    format: "png",
    opts: { background: true },
  });
  downloadBlob(blob, filename);
}
