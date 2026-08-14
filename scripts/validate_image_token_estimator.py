"""
scripts/validate_image_token_estimator.py

One-off validation script for Project SLATE's B2 requirement:
"validate [the estimator] against reported totals across at least twenty
requests. Report your estimator's mean absolute error."

WHY THIS EXISTS AS A SEPARATE SCRIPT, NOT PART OF THE APP:
Production goes through the OpenAI-compat shim (backend/adapters/client.py),
which flattens usage into prompt_tokens/completion_tokens/total_tokens with
no text/image split. Gemini's *native* SDK may expose that split via
usage_metadata.prompt_tokens_details — "may" because this hasn't been
confirmed against a real response yet. This script uses the native SDK
ONLY to gather ground truth for validation — it never runs in the request
path and has no bearing on production architecture.

MANDATORY FIRST STEP — run --sanity-check before anything else:
    python scripts/validate_image_token_estimator.py --sanity-check --images path/to/one.png

This checks ONE image, prints the raw usage_metadata object, and tells
you explicitly whether prompt_tokens_details exists at all on your
installed SDK version. The documented UsageMetadata properties in
google-genai's own docs (checked while writing this) list
prompt_token_count / candidates_token_count / total_token_count /
thoughts_token_count — prompt_tokens_details was NOT confirmed present.
If your sanity check shows it's missing, do not run the full batch —
this approach doesn't work on your SDK version, and the honest thing to
do is document in METRICS.md that no real modality-split ground truth is
available through either provider (Ollama or Gemini), rather than continue
spending quota chasing it.

USAGE (only after the sanity check passes):
    pip install google-genai pillow --break-system-packages
    export GEMINI_API_KEY=...
    python scripts/validate_image_token_estimator.py --images "traces/benchmark_crops/*.png"

Cite the resulting MAE + n in METRICS.md, along with this scope note:
"Validated against Gemini's native API only; the same estimator is applied
unvalidated-but-consistently to Ollama/local runs, since local runtimes do
not expose a comparable modality-level token breakdown."
"""

import argparse
import csv
import glob
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# --- Wire this up to your actual estimator -------------------------------
# Real signature, confirmed against backend/estimator.py:
#   estimate_image_tokens(width_px: int, height_px: int, rule: TilingRule = DEFAULT_RULE) -> int
# It is purely dimension-based — it does NOT take a format string. An
# earlier version of this script passed the image format into the `rule`
# slot, which crashes (AttributeError: 'str' object has no attribute
# 'tile_px') the instant it runs. Confirmed by actually running it, not
# just reading it.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from estimator import estimate_image_tokens  # type: ignore
except ImportError:
    print("[warn] Could not import estimate_image_tokens from backend/estimator.py.")
    print("       Ground-truth values will still be collected; estimates will be None.")
    estimate_image_tokens = None

try:
    from google import genai
except ImportError:
    print("Install the SDK first: pip install google-genai --break-system-packages")
    sys.exit(1)

from PIL import Image


@dataclass
class ValidationRow:
    image_path: str
    width: int
    height: int
    ground_truth_image_tokens: "int | None"
    estimated_image_tokens: "int | None"
    abs_error: "int | None"
    total_prompt_tokens: int
    thoughts_tokens: int


def run_sanity_check(client: "genai.Client", model: str, image_path: str) -> None:
    """Mandatory first step — see module docstring. Prints the raw
    usage_metadata object and explicitly reports whether the field this
    whole script depends on actually exists on this SDK version."""
    img = Image.open(image_path)
    response = client.models.generate_content(
        model=model,
        contents=["Describe this image in one sentence.", img],
    )
    usage = response.usage_metadata

    print("=" * 70)
    print("RAW usage_metadata object:")
    print(usage)
    print("=" * 70)

    has_details = hasattr(usage, "prompt_tokens_details") and getattr(usage, "prompt_tokens_details")
    if has_details:
        print("\n✓ prompt_tokens_details IS present — the modality-split approach")
        print("  this script relies on should work. Proceed to the full batch run.")
    else:
        print("\n✗ prompt_tokens_details is MISSING or empty on this response.")
        print("  This means Gemini's Python SDK is not exposing the image/text")
        print("  token split for this model/SDK version. DO NOT run the full")
        print("  batch expecting real ground truth — it won't be there.")
        print("  Document this finding in METRICS.md as a limitation instead:")
        print('  "No modality-level token ground truth was available through')
        print('  either Ollama or Gemini\'s accessible APIs; the estimator is')
        print('  applied consistently but unvalidated against real image-token')
        print('  counts."')


def get_ground_truth(client: "genai.Client", model: str, image_path: str) -> tuple["int | None", int, int]:
    """
    Returns (image_modality_tokens_or_None, total_prompt_tokens, thoughts_tokens)
    for one image, read from Gemini's native usage_metadata. Returns None
    for image tokens (not 0) if prompt_tokens_details isn't present — 0
    would silently look like a valid ground-truth value in the CSV output
    and corrupt the MAE calculation; None makes the gap visible instead.
    """
    img = Image.open(image_path)
    response = client.models.generate_content(
        model=model,
        contents=["Describe this image in one sentence.", img],
    )

    usage = response.usage_metadata

    image_tokens = None
    details = getattr(usage, "prompt_tokens_details", None) or []
    for entry in details:
        modality = getattr(entry, "modality", None)
        if str(modality).upper() == "IMAGE":
            image_tokens = getattr(entry, "token_count", None)
            break

    total_prompt = getattr(usage, "prompt_token_count", 0)
    thoughts = getattr(usage, "thoughts_token_count", 0) or 0
    return image_tokens, total_prompt, thoughts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", required=True,
                         help="Glob pattern(s) for test crop images, e.g. traces/benchmark_crops/*.png")
    parser.add_argument("--model", default="gemini-3.6-flash",
                         help="Native model name to validate against (check current availability).")
    parser.add_argument("--out", default="traces/estimator_validation.csv")
    parser.add_argument("--sanity-check", action="store_true",
                         help="Check ONE image and report whether prompt_tokens_details exists "
                              "on this SDK before spending quota on a full batch. Run this first.")
    args = parser.parse_args()

    image_paths: list[str] = []
    for pattern in args.images:
        image_paths.extend(sorted(glob.glob(pattern)))

    if not image_paths:
        print(f"No images matched: {args.images}")
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY first.")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    if args.sanity_check:
        run_sanity_check(client, args.model, image_paths[0])
        return

    if len(image_paths) < 20:
        print(f"[warn] Only {len(image_paths)} images found — B2 wants at least 20 requests. "
              f"Add more crops before citing this run in METRICS.md.")

    # Skip images already validated in a previous run of this script — the
    # whole point of appending is not re-spending quota on the same image.
    out_path = Path(args.out)
    already_done: set[str] = set()
    if out_path.exists():
        with open(out_path, "r", newline="") as f:
            already_done = {row["image_path"] for row in csv.DictReader(f)}
        if already_done:
            print(f"[resume] {len(already_done)} image(s) already in {args.out} — skipping those.")

    image_paths = [p for p in image_paths if p not in already_done]
    if not image_paths:
        print("Nothing new to process — every matched image is already in the output file.")
        return

    rows: list[ValidationRow] = []
    missing_ground_truth = 0
    for path in image_paths:
        try:
            gt_image_tokens, total_prompt, thoughts = get_ground_truth(client, args.model, path)
        except Exception as e:
            print(f"[skip] {path}: {e}")
            continue

        if gt_image_tokens is None:
            missing_ground_truth += 1

        with Image.open(path) as im:
            width, height = im.size

        estimated = None
        abs_error = None
        if estimate_image_tokens is not None:
            estimated = estimate_image_tokens(width, height)
            if gt_image_tokens is not None:
                abs_error = abs(estimated - gt_image_tokens)

        row = ValidationRow(
            image_path=path, width=width, height=height,
            ground_truth_image_tokens=gt_image_tokens,
            estimated_image_tokens=estimated, abs_error=abs_error,
            total_prompt_tokens=total_prompt, thoughts_tokens=thoughts,
        )
        rows.append(row)
        print(f"{path}: ground_truth={gt_image_tokens} estimated={estimated} abs_error={abs_error}")

    if not rows:
        print("No new results collected.")
        return

    if missing_ground_truth == len(rows):
        print("\n[warn] EVERY new image came back with no ground-truth image token count.")
        print("       prompt_tokens_details is not available through this SDK/model —")
        print("       re-run with --sanity-check to confirm, then document this as a")
        print("       limitation in METRICS.md rather than citing a fabricated MAE.")

    # Append mode: write the header only if the file doesn't exist yet.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not out_path.exists()
    with open(out_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        if write_header:
            writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))


    valid_errors = [r.abs_error for r in rows if r.abs_error is not None]
    if valid_errors:
        mae = sum(valid_errors) / len(valid_errors)
        print(f"\nThis run — MAE over {len(valid_errors)} new requests: {mae:.1f} tokens")

    # Cumulative MAE across every run so far (this is the number that goes
    # in METRICS.md — reading it back from disk, not from `rows`, is what
    # makes append mode actually mean something).
    with open(out_path, "r", newline="") as f:
        all_rows = list(csv.DictReader(f))
    all_errors = [
        abs(int(r["estimated_image_tokens"]) - int(r["ground_truth_image_tokens"]))
        for r in all_rows
        if r["ground_truth_image_tokens"] not in ("", "None") and r["estimated_image_tokens"] not in ("", "None")
    ]
    if all_errors:
        cumulative_mae = sum(all_errors) / len(all_errors)
        print(f"Cumulative — MAE over {len(all_errors)} total requests across all runs: {cumulative_mae:.1f} tokens")
        print(f"Results in {args.out} — cite the CUMULATIVE MAE + n in METRICS.md, not just this run's.")
    else:
        print("\n[warn] No valid ground-truth/estimate pairs collected — see warnings above.")


if __name__ == "__main__":
    main()
