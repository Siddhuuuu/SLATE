import { useRef } from "react";
import type { Editor } from "tldraw";
import { Download, PencilRuler, Sparkles, Upload, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { exportConfirmedPng, loadSnapshotFromFile, saveSnapshotToFile } from "@/components/canvas/persistence";

export interface TopBarProps {
  editor: Editor | null;
  onGenerateNow?: () => void;
}

export function TopBar({ editor, onGenerateNow }: TopBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <TooltipProvider delayDuration={300}>
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-chrome px-4">
        <div className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <PencilRuler className="h-4 w-4 text-primary" />
          SLATE
        </div>

        <Separator orientation="vertical" className="h-5" />

        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                disabled={!editor}
                onClick={() => editor && saveSnapshotToFile(editor)}
              >
                <Download className="h-3.5 w-3.5" />
                Save
              </Button>
            </TooltipTrigger>
            <TooltipContent>Download canvas as JSON (confirmed content only)</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="sm" disabled={!editor} onClick={() => fileInputRef.current?.click()}>
                <Upload className="h-3.5 w-3.5" />
                Load
              </Button>
            </TooltipTrigger>
            <TooltipContent>Load a previously saved canvas JSON</TooltipContent>
          </Tooltip>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file && editor) void loadSnapshotFromFile(editor, file);
              e.target.value = "";
            }}
          />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                disabled={!editor}
                onClick={() => editor && void exportConfirmedPng(editor)}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Export PNG
              </Button>
            </TooltipTrigger>
            <TooltipContent>Export as PNG (confirmed content only, drafts excluded)</TooltipContent>
          </Tooltip>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="font-mono text-[11px] text-muted-foreground tabular">
            idle-trigger ~1000ms
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="secondary" size="sm" disabled={!onGenerateNow} onClick={() => onGenerateNow?.()}>
                <Zap className="h-3.5 w-3.5" />
                Generate now
                <kbd className="ml-0.5 rounded border border-border/70 bg-muted px-1 font-mono text-[10px] leading-tight text-muted-foreground">
                  {navigator.platform.includes("Mac") ? "⌘" : "Ctrl"}+↵
                </kbd>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Skip the idle timer and capture the region immediately</TooltipContent>
          </Tooltip>
        </div>
      </header>
    </TooltipProvider>
  );
}
