import { useMemo } from "react";
import katex from "katex";

/**
 * Splits on $$...$$ (block) and $...$ (inline) delimiters and renders the
 * math segments with KaTeX, leaving everything else as plain text. Models
 * mix prose and LaTeX freely in their output (see the E=mc² -> "$$E^2 =
 * (pc)^2 + (mc^2)^2$$" example) — this is a text-vs-math splitter, not a
 * full markdown renderer, deliberately scoped to just that.
 */
function renderSegments(text: string): { type: "text" | "math"; content: string; display: boolean }[] {
  const segments: { type: "text" | "math"; content: string; display: boolean }[] = [];
  // Block math ($$...$$) first, since $...$ would otherwise match its
  // inner boundaries and mangle the split.
  const pattern = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", content: text.slice(lastIndex, match.index), display: false });
    }
    if (match[1] !== undefined) {
      segments.push({ type: "math", content: match[1], display: true });
    } else {
      segments.push({ type: "math", content: match[2], display: false });
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", content: text.slice(lastIndex), display: false });
  }
  return segments;
}

export function MathText({ text, className }: { text: string; className?: string }) {
  const segments = useMemo(() => renderSegments(text), [text]);

  return (
    <span className={className}>
      {segments.map((seg, i) => {
        if (seg.type === "text") return <span key={i}>{seg.content}</span>;

        let html: string;
        try {
          html = katex.renderToString(seg.content, {
            throwOnError: false,
            displayMode: seg.display,
          });
        } catch {
          // Malformed LaTeX mid-stream (a token boundary can land inside
          // an incomplete $$...$$ span while still streaming) — fall back
          // to showing the raw text rather than crashing the draft shape.
          return <span key={i}>{seg.display ? `$$${seg.content}$$` : `$${seg.content}$`}</span>;
        }
        return (
          <span
            key={i}
            className={seg.display ? "my-1 block" : "inline"}
            // eslint-disable-next-line react/no-danger -- katex.renderToString output, not user HTML
            dangerouslySetInnerHTML={{ __html: html }}
          />
        );
      })}
    </span>
  );
}
