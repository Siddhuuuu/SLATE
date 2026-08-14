/**
 * frame_timing_stress_test.js
 *
 * Paste this into your browser's DevTools console while SLATE is open
 * and the tldraw editor has mounted. Produces the "measured frame timing
 * with 5,000+ strokes" number the README requires — this can't be
 * faked or estimated, it needs a real browser actually rendering.
 *
 * What it does:
 *   1. Grabs the live tldraw editor instance off the page.
 *   2. Creates 5,000 small draw shapes scattered across a large area.
 *   3. Samples requestAnimationFrame deltas for 3 seconds while
 *      programmatically panning the camera, to simulate real pan/zoom
 *      interaction under load.
 *   4. Prints p50/p95/mean frame time and FPS.
 *
 * Copy the printed numbers straight into README.md's "Interaction
 * latency" section — don't round favorably, don't cherry-pick a good run.
 */
(async function stressTestFrameTiming() {
  // Requires the dev-only hook in Canvas.tsx's onMount (only active in
  // `npm run dev`, not a production build) — window.__slateEditor is the
  // real editor instance, not a guess about tldraw's internal DOM
  // attachment (verified against tldraw's own source: it does not
  // expose the editor via a container DOM property by convention).
  const editor = window.__slateEditor;
  if (!editor) {
    console.error(
      "window.__slateEditor not found. Make sure you're running `npm run dev` " +
        "(not a production build) and Canvas.tsx has mounted at least once."
    );
    return;
  }

  const N = 5000;
  console.log(`Creating ${N} draw shapes...`);
  const t0 = performance.now();

  const shapes = [];
  for (let i = 0; i < N; i++) {
    const x = Math.random() * 20000 - 10000;
    const y = Math.random() * 20000 - 10000;
    shapes.push({
      id: editor.createShapeId(),
      type: "draw",
      x,
      y,
      props: {
        segments: [
          {
            type: "free",
            points: [
              { x: 0, y: 0, z: 0.5 },
              { x: 10, y: 10, z: 0.5 },
              { x: 20, y: 0, z: 0.5 },
            ],
          },
        ],
        color: "black",
        size: "m",
        isComplete: true,
      },
    });
  }
  // Batch in chunks — creating 5000 shapes in one createShapes call can
  // itself stall the main thread in a way that's about creation cost,
  // not steady-state render cost, which would contaminate the reading.
  const CHUNK = 250;
  for (let i = 0; i < shapes.length; i += CHUNK) {
    editor.createShapes(shapes.slice(i, i + CHUNK));
  }
  const createMs = performance.now() - t0;
  console.log(`Created ${N} shapes in ${createMs.toFixed(0)}ms (one-time cost, not part of frame timing).`);

  // Let creation settle, then measure steady-state frame time while
  // panning — this is the number that actually matters for "does it
  // stay responsive," not creation time.
  await new Promise((r) => setTimeout(r, 500));

  console.log("Measuring frame timing over 3s while panning...");
  const frameTimes = [];
  let lastFrame = performance.now();
  let panning = true;
  let angle = 0;

  function panStep() {
    if (!panning) return;
    const camera = editor.getCamera();
    angle += 0.05;
    editor.setCamera({ ...camera, x: camera.x + Math.cos(angle) * 8, y: camera.y + Math.sin(angle) * 8 });

    const now = performance.now();
    frameTimes.push(now - lastFrame);
    lastFrame = now;
    requestAnimationFrame(panStep);
  }
  requestAnimationFrame(panStep);

  await new Promise((r) => setTimeout(r, 3000));
  panning = false;

  frameTimes.sort((a, b) => a - b);
  const p50 = frameTimes[Math.floor(frameTimes.length * 0.5)];
  const p95 = frameTimes[Math.floor(frameTimes.length * 0.95)];
  const mean = frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length;

  console.log("=".repeat(50));
  console.log(`Shape count on canvas: ${editor.getCurrentPageShapeIds().size}`);
  console.log(`Samples: ${frameTimes.length}`);
  console.log(`p50 frame time: ${p50.toFixed(2)}ms  (${(1000 / p50).toFixed(1)} fps)`);
  console.log(`p95 frame time: ${p95.toFixed(2)}ms  (${(1000 / p95).toFixed(1)} fps)`);
  console.log(`mean frame time: ${mean.toFixed(2)}ms  (${(1000 / mean).toFixed(1)} fps)`);
  console.log("=".repeat(50));
  console.log("Copy these numbers into README.md's Interaction latency section.");
  console.log("To clean up the 5000 test shapes: editor.deleteShapes(editor.getCurrentPageShapeIds())");
})();
