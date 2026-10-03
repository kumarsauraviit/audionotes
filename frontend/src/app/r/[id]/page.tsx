"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertTriangle,
  Check,
  Clock,
  Download,
  FileText,
  ListChecks,
  LoaderCircle,
  LogIn,
  Pencil,
  RefreshCw,
  Sparkles,
  Volume2,
  X,
} from "lucide-react";

import { AppShell, TopBreadcrumb } from "@/components/AppChrome";
import { AudioPlayer } from "@/components/AudioPlayer";
import { TranscriptView } from "@/components/TranscriptView";
import { AskPanel } from "@/components/AskPanel";
import { MarkdownContent } from "@/components/MarkdownContent";
import { TagEditor } from "@/components/TagEditor";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { useAuth } from "@/context/AuthContext";
import {
  useDeleteNote,
  useNote,
  useRenameNote,
  useRetryNote,
  useSummaryAudio,
  useUpdateNoteOptions,
} from "@/hooks/useNotes";
import { audioUrl, exportUrl, summaryAudioUrl } from "@/lib/api";
import {
  errorCopy,
  formatClock,
  formatDuration,
  isProcessingStatus,
  languageLabel,
  prettyDate,
  prettySize,
  statusLabel,
  type NoteStatus,
} from "@/lib/notes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

function isProcessing(status: NoteStatus) {
  return isProcessingStatus(status);
}

function stageIndex(status: string) {
  const order = ["queued", "transcribing", "summarizing", "indexing", "complete"];
  const index = order.indexOf(status);
  return index === -1 ? 0 : index;
}

function talkTime(segments: { speaker_id?: number | null; start_time: number; end_time: number }[]) {
  const totals = new Map<number, number>();
  segments.forEach((segment) => {
    if (segment.speaker_id == null) return;
    const duration = Math.max(0, segment.end_time - segment.start_time);
    totals.set(segment.speaker_id, (totals.get(segment.speaker_id) ?? 0) + duration);
  });
  return totals;
}

export default function ReaderPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = typeof params.id === "string" ? params.id : params.id?.[0] ?? "";

  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { showToast } = useWorkspace();
  const { data: note, isLoading, isError } = useNote(id, isAuthenticated);
  const renameNote = useRenameNote();
  const deleteNote = useDeleteNote();
  const retryNote = useRetryNote();
  const updateOptions = useUpdateNoteOptions();
  const summaryAudio = useSummaryAudio(id);

  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [playhead, setPlayhead] = useState(0);
  const [seekRequest, setSeekRequest] = useState<{ t: number; nonce: number } | null>(null);
  const previousStatus = useRef<string | null>(null);
  const initialSeekDone = useRef(false);

  // Deep link support: /r/<id>?t=83 jumps to that second.
  useEffect(() => {
    if (!note || initialSeekDone.current) return;
    const seconds = Number(new URLSearchParams(window.location.search).get("t"));
    if (Number.isFinite(seconds) && seconds > 0) {
      setSeekRequest({ t: seconds, nonce: Date.now() });
    }
    initialSeekDone.current = true;
  }, [note]);

  useEffect(() => {
    if (!note) return;
    if (previousStatus.current && previousStatus.current !== note.status && note.status === "complete") {
      toast.success(`“${note.filename}” is ready to read.`);
    }
    previousStatus.current = note.status;
  }, [note]);

  const seekTo = useCallback((t: number) => setSeekRequest({ t, nonce: Date.now() }), []);

  const speakers = useMemo(() => {
    if (!note?.segments) return [] as { id: number; label: string; seconds: number }[];
    const totals = talkTime(note.segments);
    const labels = note.speaker_labels ?? {};
    return Array.from(totals.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([speakerId, seconds]) => ({
        id: speakerId,
        label: labels[String(speakerId)] || `Speaker ${speakerId}`,
        seconds,
      }));
  }, [note]);

  const saveRename = async () => {
    if (!note) return;
    const trimmed = editName.trim();
    if (!trimmed) return;
    if (trimmed === note.filename) {
      setEditing(false);
      return;
    }
    await renameNote.mutateAsync({ id: note.id, filename: trimmed });
    setEditing(false);
  };

  const remove = async () => {
    if (!note) return;
    if (!window.confirm("Delete this recording? Its transcript, summary, and audio will be removed.")) return;
    await deleteNote.mutateAsync(note.id);
    router.push("/");
  };

  const crumb = <TopBreadcrumb current={note?.filename ?? "Recording"} />;
  if (authLoading || (isAuthenticated && isLoading)) {
    return (
      <AppShell center={crumb}>
        <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
          <LoaderCircle size={18} className="animate-spin" /> Loading recording…
        </div>
      </AppShell>
    );
  }

  if (!isAuthenticated) {
    return (
      <AppShell center={crumb}>
        <div className="mx-auto mt-16 max-w-md text-center">
          <h2 className="text-lg font-semibold">Log in to read this recording</h2>
          <p className="mt-1 text-sm text-muted-foreground">Recordings are saved to your account.</p>
          <Button asChild className="mt-4">
            <Link href={`/login?redirect=${encodeURIComponent(`/r/${id}`)}`}>
              <LogIn size={15} /> Log in
            </Link>
          </Button>
        </div>
      </AppShell>
    );
  }

  if (isError || !note) {
    return (
      <AppShell center={crumb}>
        <div className="mx-auto mt-16 max-w-md text-center">
          <h2 className="text-lg font-semibold">This recording isn’t available</h2>
          <p className="mt-1 text-sm text-muted-foreground">It may have been deleted, or the link is incorrect.</p>
          <Button asChild className="mt-4">
            <Link href="/">Back to library</Link>
          </Button>
        </div>
      </AppShell>
    );
  }

  const processing = isProcessing(note.status);
  const totalSpeakerSeconds = speakers.reduce((sum, speaker) => sum + speaker.seconds, 0);
  const stage = stageIndex(note.status);

  return (
    <AppShell center={crumb}>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-w-0 flex-col gap-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              {editing ? (
                <div className="flex items-center gap-1.5">
                  <Input
                    value={editName}
                    onChange={(event) => setEditName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void saveRename();
                      if (event.key === "Escape") setEditing(false);
                    }}
                    autoFocus
                    className="h-9 w-72"
                  />
                  <Button size="icon-sm" onClick={() => void saveRename()} aria-label="Save name">
                    <Check size={14} />
                  </Button>
                  <Button size="icon-sm" variant="ghost" onClick={() => setEditing(false)} aria-label="Cancel">
                    <X size={14} />
                  </Button>
                </div>
              ) : (
                <>
                  <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">{note.filename}</h1>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => {
                      setEditing(true);
                      setEditName(note.filename);
                    }}
                    aria-label="Rename recording"
                  >
                    <Pencil size={13} />
                  </Button>
                </>
              )}
            </div>
            <Badge
              variant={
                note.status === "complete"
                  ? "success"
                  : note.status === "complete_with_warnings"
                    ? "mark"
                    : note.status === "failed"
                      ? "destructive"
                      : "secondary"
              }
              aria-live="polite"
            >
              {note.status === "complete" && <Check size={11} />}
              {processing && <LoaderCircle size={11} className="animate-spin" />}
              {statusLabel(note.status)}
            </Badge>
          </div>

          {processing && (
            <div className="rounded-lg border border-border bg-paper p-4" role="status" aria-live="polite">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 font-medium">
                  <LoaderCircle size={14} className="animate-spin" />
                  {note.progress_message || "Working on it"}
                </span>
                <span className="tabular-nums text-muted-foreground">
                  {typeof note.progress_percent === "number" ? `${note.progress_percent}%` : `Step ${stage + 1} of 5`}
                </span>
              </div>
              <Progress value={note.progress_percent ?? stage * 20} />
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                {note.eta_seconds ? (
                  <span className="flex items-center gap-1">
                    <Clock size={12} /> about {formatDuration(note.eta_seconds)} remaining
                  </span>
                ) : null}
                {note.gnani_status ? <span>Gnani: {note.gnani_status}</span> : null}
                {note.retry_count ? <span>Attempt {note.retry_count + 1}</span> : null}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                You can leave this tab open — we’ll mark it ready when it’s done.
              </p>
            </div>
          )}

          {note.status === "failed" && (
            <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
              <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-destructive/10 text-destructive">
                <AlertTriangle size={15} />
              </span>
              <div className="flex-1">
                <strong className="text-sm">We couldn’t finish this recording</strong>
                <p className="mt-0.5 text-sm text-destructive">
                  {errorCopy(note.error_code, note.error_message)}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-3"
                  onClick={() => retryNote.mutate(note.id)}
                  disabled={retryNote.isPending}
                >
                  <RefreshCw size={13} /> Try again
                </Button>
              </div>
            </div>
          )}

          <AudioPlayer
            src={audioUrl(note)}
            filename={note.filename}
            initialDuration={note.duration_seconds ?? note.segments?.at(-1)?.end_time ?? 0}
            onTime={setPlayhead}
            seek={seekRequest}
          />

          {note.status === "complete_with_warnings" && (
            <div className="flex items-start gap-2 rounded-lg border border-orange/30 bg-orange/5 p-3 text-sm">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-orange" />
              <span>The transcript is ready, but the summary could not be generated.</span>
            </div>
          )}

          <section className="rounded-lg border border-border bg-paper p-5">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles size={15} className="text-accent" /> Summary
                {note.summary_model && <Badge variant="outline">{note.summary_model}</Badge>}
              </div>
              {note.summary && (
                <div className="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => summaryAudio.mutate(undefined)}
                    disabled={summaryAudio.isPending}
                    aria-busy={summaryAudio.isPending}
                  >
                    {summaryAudio.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Volume2 size={13} />}
                    {summaryAudio.isPending
                      ? "Generating audio…"
                      : note.has_summary_audio
                        ? "Regenerate audio"
                        : "Generate audio"}
                  </Button>
                </div>
              )}
            </div>
            {note.summary ? (
              <>
                <MarkdownContent source={note.summary} />
                {note.has_summary_audio && (
                  <audio className="mt-3 w-full" controls preload="metadata" src={summaryAudioUrl(note)} />
                )}
              </>
            ) : processing ? (
              <div className="flex flex-col gap-2">
                <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
                <div className="h-3 w-full animate-pulse rounded bg-muted" />
                <div className="h-3 w-4/5 animate-pulse rounded bg-muted" />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                A summary wasn’t generated for this recording. The transcript is still available below.
              </p>
            )}
          </section>

          {note.extraction &&
            (note.extraction.action_items.length > 0 ||
              note.extraction.decisions.length > 0 ||
              note.extraction.dates.length > 0) && (
              <section className="rounded-lg border border-border bg-paper p-5">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <ListChecks size={15} className="text-accent" /> Extracted from this recording
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <ExtractionList title="Action items" items={note.extraction.action_items} />
                  <ExtractionList title="Decisions" items={note.extraction.decisions} />
                  <ExtractionList title="Dates & deadlines" items={note.extraction.dates} />
                  {note.extraction.entities?.people?.length ? (
                    <ExtractionList title="People" items={note.extraction.entities.people} />
                  ) : null}
                </div>
              </section>
            )}

          {note.chapters && note.chapters.length > 0 && (
            <section className="rounded-lg border border-border bg-paper p-5">
              <div className="mb-3 text-sm font-semibold">Chapters</div>
              <ol className="flex flex-col gap-1">
                {note.chapters.map((chapter, index) => (
                  <li key={`${chapter.title}-${index}`}>
                    <button
                      type="button"
                      onClick={() => seekTo(chapter.start_time)}
                      className="flex w-full items-baseline gap-3 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted"
                    >
                      <span className="tabular-nums text-xs text-muted-foreground">{formatClock(chapter.start_time)}</span>
                      <span className="flex-1 text-sm font-medium">{chapter.title}</span>
                      {chapter.summary && (
                        <span className="hidden max-w-[40%] truncate text-xs text-muted-foreground sm:block">
                          {chapter.summary}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <section className="rounded-lg border border-border bg-paper p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <FileText size={15} className="text-accent" /> Transcript
                {note.transcript && (
                  <span className="text-xs font-normal text-muted-foreground">
                    {note.transcript.trim().split(/\s+/).filter(Boolean).length} words
                  </span>
                )}
                {note.transcription_engine && <Badge variant="outline">{note.transcription_engine}</Badge>}
                {note.detected_language && <Badge variant="outline">{languageLabel(note.detected_language)}</Badge>}
              </div>
              {note.transcript && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm" variant="outline">
                      <Download size={13} /> Export
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuLabel>Download transcript</DropdownMenuLabel>
                    <DropdownMenuItem asChild>
                      <a href={exportUrl(note, "txt")} download>Plain text (.txt)</a>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <a href={exportUrl(note, "md")} download>Markdown (.md)</a>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild disabled={!note.segments?.length}>
                      <a href={exportUrl(note, "srt")} download>Subtitles (.srt)</a>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild disabled={!note.segments?.length}>
                      <a href={exportUrl(note, "vtt")} download>Subtitles (.vtt)</a>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
            {note.transcript ? (
              <TranscriptView
                transcript={note.transcript}
                segments={note.segments}
                speakerLabels={note.speaker_labels}
                filename={note.filename}
                playhead={playhead}
                onSeek={seekTo}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                Your transcript will appear here once the audio has been processed.
              </p>
            )}
          </section>
        </div>

        <aside className="flex flex-col gap-4">
          <div className="rounded-lg border border-border bg-paper p-4">
            <h3 className="mb-3 text-sm font-semibold">About this recording</h3>
            <dl className="flex flex-col gap-2 text-sm">
              <Meta label="Language" value={languageLabel(note.detected_language || note.language_code)} />
              {note.detected_language && note.detected_language !== note.language_code && (
                <Meta label="Requested" value={languageLabel(note.language_code)} />
              )}
              <Meta label="Added" value={prettyDate(note.created_at)} />
              <Meta label="Size" value={prettySize(note.file_size)} />
              <Meta label="Length" value={formatDuration(note.duration_seconds ?? note.segments?.at(-1)?.end_time ?? 0)} />
              {note.with_diarization && <Meta label="Speakers" value="Separated" />}
              {note.with_denoise && <Meta label="Cleanup" value="Denoised" />}
            </dl>

            {speakers.length > 0 && (
              <>
                <Separator className="my-3" />
                <h4 className="mb-2 text-xs font-semibold text-muted-foreground">Talk time</h4>
                <ul className="flex flex-col gap-2">
                  {speakers.map((speaker) => {
                    const percent = totalSpeakerSeconds ? Math.round((speaker.seconds / totalSpeakerSeconds) * 100) : 0;
                    return (
                      <li key={speaker.id} className="text-xs">
                        <div className="mb-1 flex justify-between">
                          <span className="font-medium">{speaker.label}</span>
                          <span className="tabular-nums text-muted-foreground">{percent}%</span>
                        </div>
                        <Progress value={percent} className="h-1.5" />
                      </li>
                    );
                  })}
                </ul>
              </>
            )}

            <Separator className="my-3" />
            <h4 className="mb-2 text-xs font-semibold text-muted-foreground">Tags</h4>
            <TagEditor
              tags={note.tags ?? []}
              onChange={(next) => updateOptions.mutate({ id: note.id, tags: next })}
              disabled={updateOptions.isPending}
            />

            <Separator className="my-3" />
            <Button variant="ghost" size="sm" className="w-full text-destructive hover:bg-destructive/10" onClick={() => void remove()}>
              Delete recording
            </Button>
          </div>

          <AskPanel
            noteId={note.id}
            hasTranscript={Boolean(note.transcript?.trim())}
            onSeek={seekTo}
          />
        </aside>
      </div>
    </AppShell>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

function ExtractionList({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-semibold text-muted-foreground">{title}</h4>
      <ul className="flex flex-col gap-1 text-sm">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
