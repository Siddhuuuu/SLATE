import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/**
 * Renders draft text as Markdown, with $...$ / $$...$$ math spans
 * rendered via KaTeX — the brief's A4 requirement is "at least Markdown
 * and LaTeX." remark-math + rehype-katex handle both in one pipeline
 * rather than hand-rolling a math-only splitter for a problem that's
 * really "parse markdown, and math is one of its node types."
 *
 * throwOnError: false matters specifically for streaming — a token
 * boundary can land mid-$$...$$ span while a draft is still streaming in,
 * which would otherwise crash the render on a malformed/incomplete
 * expression. It falls back to rendering the raw source for that span
 * instead, exactly like the custom filter this replaced did.
 */
export function MarkdownContent({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
