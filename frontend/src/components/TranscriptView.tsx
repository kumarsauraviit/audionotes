"use client";

import { useState } from "react";
import { Copy, Search, X } from "lucide-react";

import { countMatches, formatClock, type Segment } from "@/lib/notes";
import { useWorkspace } from "./WorkspaceProvider";
import { Highlight } from "./Highlight";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SPEAKER_STYLES = [
  "text-accent",
  "text-orange",
  "text-green",
  "text-destructive",
];

export function TranscriptView({
  transcript,
  segments,
  speakerLabels,
  filename,
  playhead,
  onSeek,
  showSpeakers = true,
}: {
  transcript: string;
  segments?: Segment[] | null;
  speakerLabels?: Record<string, string> | null;
  filename: string;
  playhead: number;
  onSeek: (t: number) => void;
  showSpeakers?: boolean;
}) {
  const { showToast } = useWorkspace();
  const [query, setQuery] = useState("");
  const matches = countMatches(transcript, query);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(transcript);
      showToast("Transcript copied to clipboard.");
    } catch {
      showToast("Could not copy the transcript.", "error");
    }
  };

  const hasSegments = Boolean(segments && segments.length > 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="relative w-full sm:max-w-xs">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find in transcript…"
            aria-label="Find in transcript"
            className="h-9 pl-8 text-sm"
          />
          {query && (
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground hover:bg-muted"
              onClick={() => setQuery("")}
              aria-label="Clear find"
            >
              <X size={12} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {query && (
            <span className="text-xs tabular-nums text-muted-foreground">
              {matches} {matches === 1 ? "match" : "matches"}
            </span>
          )}
          <Button size="sm" variant="outline" onClick={() => void copy()}>
            <Copy size={13} /> Copy
          </Button>
        </div>
      </div>

      {hasSegments ? (
        <div className="flex max-h-[560px] flex-col gap-0.5 overflow-auto pr-1">
          {segments!.map((segment, index) => {
            const active = playhead >= segment.start_time && playhead < segment.end_time;
            const speakerLabel =
              showSpeakers && segment.speaker_id != null
                ? speakerLabels?.[String(segment.speaker_id)] || `Speaker ${segment.speaker_id}`
                : null;
            const speakerClass =
              showSpeakers && segment.speaker_id != null
                ? SPEAKER_STYLES[(segment.speaker_id - 1) % SPEAKER_STYLES.length]
                : "text-muted-foreground";
            return (
              <button
                type="button"
                key={index}
                className={cn(
                  "group grid grid-cols-[52px_1fr] items-baseline gap-3 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted",
                  active && "bg-accent-wash"
                )}
                onClick={() => onSeek(segment.start_time)}
                title="Play from here"
              >
                <span className="tabular-nums text-xs text-muted-foreground">{formatClock(segment.start_time)}</span>
                <span className="font-read text-[15px] leading-relaxed">
                  {speakerLabel && (
                    <span className={cn("mr-2 text-xs font-semibold not-italic", speakerClass)}>{speakerLabel}</span>
                  )}
                  <Highlight text={segment.text} query={query} />
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="font-read text-[16px] leading-relaxed text-foreground">
          <Highlight text={transcript} query={query} />
        </p>
      )}
      <p className="text-xs text-muted-foreground">{filename}</p>
    </div>
  );
}
