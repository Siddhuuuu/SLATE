import {
  HTMLContainer,
  Rectangle2d,
  ShapeUtil,
  T,
  type Geometry2d,
  type RecordProps,
  type TLBaseShape,
  type TLResizeInfo,
  resizeBox,
} from "tldraw";

import { cn } from "@/lib/utils";
import { MarkdownContent } from "./MarkdownContent";
import type { DraftStatus } from "@/lib/types";

export const DRAFT_SHAPE_TYPE = "draft" as const;

export type DraftShape = TLBaseShape<
  "draft",
  {
    w: number;
    h: number;
    status: DraftStatus;
    text: string;
    provider: string;
    tier: string;
    requestId: string;
  }
>;

// Callbacks the app wires in once, at mount — see Canvas.tsx. Kept outside
// shape props because accept/discard need to talk to the request lifecycle
// (backend calls, SSE cleanup), not just mutate shape state.
export interface DraftShapeCallbacks {
  onAccept: (requestId: string) => void;
  onDiscard: (requestId: string) => void;
}

let callbacks: DraftShapeCallbacks = {
  onAccept: () => {},
  onDiscard: () => {},
};

export function registerDraftShapeCallbacks(next: DraftShapeCallbacks) {
  callbacks = next;
}

const STATUS_LABEL: Record<DraftStatus, string> = {
  pending: "Pending",
  streaming: "Streaming",
  ready: "Ready",
  accepted: "Accepted",
  discarded: "Discarded",
  error: "Error",
};

// Tailwind's `border-*` palette can't be looked up dynamically from a JS
// string, so status -> color is an explicit table rather than a template.
const STATUS_STROKE: Record<DraftStatus, string> = {
  pending: "hsl(var(--pending))",
  streaming: "hsl(var(--streaming))",
  ready: "hsl(var(--ready))",
  accepted: "hsl(var(--ready))",
  discarded: "hsl(var(--muted-foreground))",
  error: "hsl(var(--destructive))",
};

const DASHED_STATUSES: DraftStatus[] = ["pending", "streaming"];

export class DraftShapeUtil extends ShapeUtil<DraftShape> {
  static override type = DRAFT_SHAPE_TYPE;

  static override props: RecordProps<DraftShape> = {
    w: T.number,
    h: T.number,
    status: T.literalEnum("pending", "streaming", "ready", "accepted", "discarded", "error"),
    text: T.string,
    provider: T.string,
    tier: T.string,
    requestId: T.string,
  };

  // These are class-field arrow functions in tldraw's own ShapeUtil base
  // class (not methods) — TS enforces the override match exactly, per
  // tldraw v2.4's actual signatures.
  override canEdit = () => false;
  override canResize = () => true;
  override isAspectRatioLocked = () => false;
  override hideRotateHandle = () => true;

  getDefaultProps(): DraftShape["props"] {
    return {
      w: 280,
      h: 140,
      status: "pending",
      text: "",
      provider: "",
      tier: "",
      requestId: "",
    };
  }

  getGeometry(shape: DraftShape): Geometry2d {
    return new Rectangle2d({ width: shape.props.w, height: shape.props.h, isFilled: true });
  }

  override onResize = (shape: DraftShape, info: TLResizeInfo<DraftShape>) => {
    return resizeBox(shape, info);
  };

  component(shape: DraftShape) {
    const { status, text, provider, tier, requestId, w, h } = shape.props;
    const dashed = DASHED_STATUSES.includes(status);
    const stroke = STATUS_STROKE[status];

    return (
      <HTMLContainer style={{ width: w, height: h }}>
        <svg
          width={w}
          height={h}
          className="pointer-events-none absolute left-0 top-0"
          style={{ overflow: "visible" }}
        >
          <rect
            x={1}
            y={1}
            width={Math.max(w - 2, 0)}
            height={Math.max(h - 2, 0)}
            rx={10}
            fill="none"
            stroke={stroke}
            strokeWidth={2}
            strokeDasharray={dashed ? "6 5" : undefined}
            className={status === "streaming" ? "draft-marching-ants" : undefined}
          />
        </svg>

        <div
          className={cn(
            "relative flex h-full w-full flex-col gap-2 rounded-[10px] bg-card/95 p-3 font-sans text-foreground shadow-lg backdrop-blur-sm",
            "animate-fade-in"
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: stroke, backgroundColor: `${stroke}22` }}
            >
              {STATUS_LABEL[status]}
            </span>
            {provider && (
              <span className="font-mono text-[10px] text-muted-foreground tabular">
                {provider}
                {tier ? ` · ${tier}` : ""}
              </span>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap text-sm leading-snug">
            {text ? (
              <MarkdownContent text={text} className="prose-draft" />
            ) : (
              <span className="italic text-muted-foreground">
                {status === "pending" ? "Waiting to send…" : "Thinking…"}
              </span>
            )}
          </div>

          {status === "ready" && (
            <div className="flex justify-end gap-2 pt-1" style={{ pointerEvents: "all" }}>
              <button
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  callbacks.onDiscard(requestId);
                }}
                className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                Discard
                <kbd className="rounded border border-border/70 bg-muted px-1 font-mono text-[10px] leading-tight text-muted-foreground/80">
                  Esc
                </kbd>
              </button>
              <button
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  callbacks.onAccept(requestId);
                }}
                className="flex items-center gap-1.5 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                Accept
                <kbd className="rounded border border-primary-foreground/30 bg-primary-foreground/10 px-1 font-mono text-[10px] leading-tight">
                  ↵
                </kbd>
              </button>
            </div>
          )}
        </div>
      </HTMLContainer>
    );
  }

  indicator(shape: DraftShape) {
    return <rect width={shape.props.w} height={shape.props.h} rx={10} />;
  }
}
