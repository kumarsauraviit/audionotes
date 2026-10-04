"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AudioLines,
  Check,
  CheckSquare,
  FileAudio2,
  LoaderCircle,
  LogIn,
  MoreVertical,
  Plus,
  Search,
  Sparkles,
  Tag,
  Trash2,
} from "lucide-react";

import { AppShell } from "@/components/AppChrome";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { useAuth } from "@/context/AuthContext";
import { useDeleteNote, useLibrarySearch, useNotes, useUsage } from "@/hooks/useNotes";
import {
  errorCopy,
  formatDuration,
  isProcessingStatus,
  languageLabel,
  prettyDate,
  statusLabel,
  type Note,
  type NoteStatus,
} from "@/lib/notes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TagDialog } from "@/components/TagDialog";
import { cn } from "@/lib/utils";

type Filter = "all" | "ready" | "processing" | "failed";

function badgeVariant(status: NoteStatus) {
  if (status === "complete") return "success" as const;
  if (status === "complete_with_warnings") return "mark" as const;
  if (status === "failed") return "destructive" as const;
  return "secondary" as const;
}

function summaryExcerpt(summary: string | null) {
  if (!summary) return "";
  return summary
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#>*_`\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 150);
}

export default function LibraryPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const { openAdd } = useWorkspace();
  const { data: notes = [], isLoading: notesLoading, isError } = useNotes();
  const { data: usage } = useUsage();
  const deleteNote = useDeleteNote();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [tagNote, setTagNote] = useState<Note | null>(null);
  const [tagOpen, setTagOpen] = useState(false);
  const semantic = useLibrarySearch(query);

  const processing = notes.filter((note) => isProcessingStatus(note.status));

  // Reflect processing state in the browser tab so a long job never looks frozen.
  useEffect(() => {
    if (processing.length > 0) {
      document.title = `Processing ${processing.length} · Audio Notes`;
    } else {
      document.title = "Audio Notes | Listen less, remember more";
    }
    return () => {
      document.title = "Audio Notes | Listen less, remember more";
    };
  }, [processing.length]);

  const tags = useMemo(() => {
    const set = new Set<string>();
    notes.forEach((note) => (note.tags ?? []).forEach((tag) => set.add(tag)));
    return Array.from(set).slice(0, 12);
  }, [notes]);

  const counts = useMemo(
    () => ({
      all: notes.length,
      ready: notes.filter((note) => note.status === "complete" || note.status === "complete_with_warnings").length,
      processing: notes.filter((note) => isProcessingStatus(note.status)).length,
      failed: notes.filter((note) => note.status === "failed").length,
    }),
    [notes]
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return notes.filter((note) => {
      if (filter === "ready" && note.status !== "complete" && note.status !== "complete_with_warnings") return false;
      if (filter === "processing" && !isProcessingStatus(note.status)) return false;
      if (filter === "failed" && note.status !== "failed") return false;
      if (activeTag && !(note.tags ?? []).includes(activeTag)) return false;
      if (!q) return true;
      return (
        note.filename.toLowerCase().includes(q) ||
        (note.transcript ?? "").toLowerCase().includes(q) ||
        (note.summary ?? "").toLowerCase().includes(q)
      );
    });
  }, [notes, filter, query, activeTag]);

  const filters: { key: Filter; label: string; count: number }[] = [
    { key: "all", label: "All", count: counts.all },
    { key: "ready", label: "Ready", count: counts.ready },
    { key: "processing", label: "Processing", count: counts.processing },
    { key: "failed", label: "Failed", count: counts.failed },
  ];

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectMode = () => {
    setSelectMode((current) => {
      if (current) setSelected(new Set());
      return !current;
    });
  };

  const selectAllVisible = () =>
    setSelected((current) => {
      const next = new Set(current);
      visible.forEach((note) => next.add(note.id));
      return next;
    });

  const openTags = (note: Note) => {
    setTagNote(note);
    setTagOpen(true);
  };

  const deleteSelected = async () => {
    for (const id of Array.from(selected)) {
      await deleteNote.mutateAsync(id).catch(() => undefined);
    }
    setSelected(new Set());
  };

  if (!isLoading && !isAuthenticated) {
    return (
      <AppShell>
        <div className="mx-auto mt-16 max-w-md text-center">
          <span className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-accent-wash text-accent">
            <AudioLines size={26} />
          </span>
          <h2 className="text-xl font-semibold">Log in to open your library</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Recordings you add are saved to your account, with their transcripts, summaries, and answers.
          </p>
          <Button asChild className="mt-5">
            <Link href="/login">
              <LogIn size={15} /> Log in
            </Link>
          </Button>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
            <p className="text-sm text-muted-foreground">
              Everything you’ve recorded, transcribed, and summarized.
            </p>
          </div>
          {usage && (
            <div className="text-right text-xs text-muted-foreground">
              <p>
                <span className="font-semibold text-ink tabular-nums">{usage.total_notes}</span> recordings ·{" "}
                <span className="font-semibold text-ink tabular-nums">{usage.total_audio_minutes}</span> min
              </p>
              <p className="tabular-nums">≈ ₹{usage.credits_estimate_inr.toFixed(2)} estimated Gnani usage</p>
              <p className="tabular-nums">STT ₹{usage.stt_estimate_inr.toFixed(2)} · TTS ₹{usage.tts_estimate_inr.toFixed(2)}</p>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-md">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search titles, transcripts, and summaries…"
              aria-label="Search recordings"
              className="pl-9"
            />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter recordings">
              {filters.map((item) => (
                <Button
                  key={item.key}
                  type="button"
                  role="tab"
                  aria-selected={filter === item.key}
                  variant={filter === item.key ? "default" : "outline"}
                  size="sm"
                  onClick={() => setFilter(item.key)}
                >
                  {item.label}
                  <span className="tabular-nums opacity-70">{item.count}</span>
                </Button>
              ))}
            </div>
            <Button
              type="button"
              variant={selectMode ? "default" : "outline"}
              size="sm"
              onClick={toggleSelectMode}
              className="ml-1"
            >
              {selectMode ? <Check size={14} /> : <CheckSquare size={14} />}
              {selectMode ? "Done" : "Select"}
            </Button>
          </div>
        </div>

        {tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {tags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setActiveTag(activeTag === tag ? null : tag)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs transition-colors",
                  activeTag === tag ? "border-primary bg-accent-wash text-accent-dark" : "border-border text-muted-foreground hover:bg-muted"
                )}
              >
                #{tag}
              </button>
            ))}
          </div>
        )}

        {selectMode && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-accent-wash px-4 py-2.5">
            <span className="text-sm">
              <strong className="tabular-nums">{selected.size}</strong> selected
              <span className="ml-2 text-xs text-muted-foreground">Tap a recording to select it</span>
            </span>
            <div className="flex items-center gap-1.5">
              <Button variant="ghost" size="sm" onClick={selectAllVisible}>
                <CheckSquare size={14} /> Select all
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                Clear
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => void deleteSelected()}
                disabled={selected.size === 0}
              >
                <Trash2 size={14} /> Delete
              </Button>
            </div>
          </div>
        )}

        {semantic.data && semantic.data.hits.length > 0 && query.trim().length >= 3 && (
          <div className="rounded-lg border border-border bg-paper p-4">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <Sparkles size={13} /> Matching moments across your library
            </p>
            <ul className="flex flex-col gap-2">
              {semantic.data.hits.slice(0, 4).map((hit) => (
                <li key={`${hit.note_id}-${hit.chunk_index}`}>
                  <Link
                    href={`/r/${hit.note_id}${hit.start_time != null ? `?t=${Math.floor(hit.start_time)}` : ""}`}
                    className="block rounded-md p-2 transition-colors hover:bg-muted"
                  >
                    <span className="text-xs font-medium text-primary">{hit.filename}</span>
                    <p className="line-clamp-2 text-sm text-muted-foreground">{hit.content}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        {notesLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-40 w-full" />
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-sm text-destructive">
            Could not load your library. Check your connection and try again.
          </div>
        ) : visible.length === 0 ? (
          <div className="mx-auto mt-12 max-w-md text-center">
            <span className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-muted text-muted-foreground">
              <FileAudio2 size={26} />
            </span>
            {notes.length === 0 ? (
              <>
                <h2 className="text-lg font-semibold">No recordings yet</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Add your first recording to get a transcript, a summary, and answers.
                </p>
                <Button className="mt-4" onClick={openAdd}>
                  <Plus size={15} /> Add recording
                </Button>
              </>
            ) : (
              <>
                <h2 className="text-lg font-semibold">Nothing matches</h2>
                <p className="mt-1 text-sm text-muted-foreground">Try a different search term or filter.</p>
              </>
            )}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((note) => (
              <RecordingCard
                key={note.id}
                note={note}
                selected={selected.has(note.id)}
                selectMode={selectMode}
                onToggle={() => toggleSelected(note.id)}
                onEditTags={() => openTags(note)}
              />
            ))}
          </div>
        )}
      </div>
      <TagDialog note={tagNote} open={tagOpen} onOpenChange={setTagOpen} />
    </AppShell>
  );
}

function RecordingCard({
  note,
  selected,
  selectMode,
  onToggle,
  onEditTags,
}: {
  note: Note;
  selected: boolean;
  selectMode: boolean;
  onToggle: () => void;
  onEditTags: () => void;
}) {
  const processing = isProcessingStatus(note.status);

  const content = (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {selectMode && (
            <Checkbox checked={selected} className="pointer-events-none" tabIndex={-1} aria-hidden />
          )}
        </div>
        <div className="flex items-center gap-1">
          <Badge variant={badgeVariant(note.status)}>
            {processing && <LoaderCircle size={11} className="animate-spin" />}
            {statusLabel(note.status)}
          </Badge>
          {!selectMode && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Actions for ${note.filename}`}
                  onClick={(event) => event.stopPropagation()}
                >
                  <MoreVertical size={15} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={onEditTags}>
                  <Tag size={14} /> Edit tags
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      <h2 className="line-clamp-2 text-sm font-semibold text-ink" title={note.filename}>
        {note.filename}
      </h2>
      <p className="text-xs text-muted-foreground">
        {prettyDate(note.created_at)} · {languageLabel(note.detected_language || note.language_code)}
        {note.duration_seconds ? ` · ${formatDuration(note.duration_seconds)}` : ""}
      </p>
      <p className="line-clamp-3 text-sm text-muted-foreground">
        {note.summary
          ? summaryExcerpt(note.summary)
          : processing
            ? note.progress_message || "Transcribing and summarizing…"
            : note.status === "failed"
              ? errorCopy(note.error_code, note.error_message)
              : "No summary for this recording."}
      </p>
      {(note.tags ?? []).length > 0 && (
        <div className="mt-auto flex flex-wrap gap-1 pt-1">
          {(note.tags ?? []).slice(0, 3).map((tag) => (
            <span key={tag} className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
              #{tag}
            </span>
          ))}
        </div>
      )}
    </>
  );

  const cardClass = cn(
    "group relative flex flex-col gap-2 rounded-lg border bg-paper p-4 transition-shadow",
    selected ? "border-primary ring-1 ring-primary/30" : "border-border",
    !selectMode && "hover:shadow-md"
  );

  if (selectMode) {
    return (
      <div
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        onClick={onToggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onToggle();
          }
        }}
        className={cn(cardClass, "cursor-pointer")}
      >
        {content}
      </div>
    );
  }

  return (
    <Link href={`/r/${note.id}`} className={cardClass}>
      {content}
    </Link>
  );
}
