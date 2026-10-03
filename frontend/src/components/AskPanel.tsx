"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { LoaderCircle, Send, Sparkles, Wrench } from "lucide-react";

import { useAsk } from "@/hooks/useNotes";
import { streamQuestion, type QuestionTurn } from "@/lib/api";
import { formatClock, type SourceChunk } from "@/lib/notes";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const SUGGESTIONS = [
  "What are the key points?",
  "What were the action items?",
  "Were any dates or deadlines mentioned?",
];

type Thread = {
  id: number;
  question: string;
  answer: string;
  sources: SourceChunk[];
  status?: string;
  streaming: boolean;
  error?: string;
};

function toolLabel(name: string, args?: Record<string, unknown>) {
  switch (name) {
    case "search_transcript":
      return args?.query ? `Searching for “${String(args.query)}”…` : "Searching the transcript…";
    case "read_transcript":
      return "Reading the transcript…";
    case "open_moment":
      return args?.start_time != null ? `Reading around ${formatClock(Number(args.start_time))}…` : "Reading that moment…";
    case "list_chapters":
      return "Looking at the chapters…";
    case "get_summary":
      return "Reading the summary…";
    case "get_details":
      return "Checking the details…";
    default:
      return "Working…";
  }
}

export function AskPanel({
  noteId,
  hasTranscript,
  onSeek,
}: {
  noteId: string;
  hasTranscript: boolean;
  onSeek?: (t: number) => void;
}) {
  const ask = useAsk(noteId);
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<Thread[]>([]);
  const idRef = useRef(0);

  useEffect(() => {
    setQuestion("");
    setThread([]);
  }, [noteId]);

  const update = (id: number, patch: Partial<Thread>) =>
    setThread((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const clean = question.trim();
    if (!hasTranscript || !clean) return;
    const id = (idRef.current += 1);

    const history: QuestionTurn[] = thread
      .filter((item) => item.answer)
      .map((item) => ({ question: item.question, answer: item.answer }));

    setQuestion("");
    setThread((current) => [
      ...current,
      { id, question: clean, answer: "", sources: [], streaming: true, status: "Thinking…" },
    ]);

    try {
      await streamQuestion(noteId, clean, history, (askEvent) => {
        if (askEvent.type === "tool") {
          update(id, { status: toolLabel(askEvent.name, askEvent.args) });
        } else if (askEvent.type === "sources") {
          update(id, { sources: askEvent.sources });
        } else if (askEvent.type === "token") {
          setThread((current) =>
            current.map((item) =>
              item.id === id ? { ...item, answer: item.answer + askEvent.text, status: undefined } : item
            )
          );
        } else if (askEvent.type === "error") {
          throw new Error(askEvent.message);
        }
      });
      update(id, { streaming: false, status: undefined });
    } catch {
      // Streaming failed — fall back to the non-streaming agent endpoint once.
      try {
        const result = await ask.mutateAsync({ question: clean, history });
        update(id, {
          answer: result.answer,
          sources: (result.sources as SourceChunk[]) ?? [],
          streaming: false,
          status: undefined,
        });
      } catch (error) {
        update(id, {
          streaming: false,
          status: undefined,
          error: error instanceof Error ? error.message : "We couldn’t answer that right now.",
        });
      }
    }
  };

  return (
    <section className="rounded-lg border border-border bg-paper p-4" aria-labelledby="ask-heading">
      <h3 id="ask-heading" className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Sparkles size={14} className="text-accent" /> Ask this recording
      </h3>

      {thread.length === 0 && hasTranscript && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((suggestion) => (
            <button
              type="button"
              key={suggestion}
              className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-ink"
              onClick={() => setQuestion(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <AnimatePresence initial={false}>
        {thread.map((item) => (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-3 border-b border-border pb-3 last:border-0"
          >
            <p className="text-sm font-medium">{item.question}</p>
            {item.answer ? (
              <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">{item.answer}</p>
            ) : item.status ? (
              <p className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                {item.streaming && <LoaderCircle size={12} className="animate-spin" />}
                <Wrench size={12} />
                {item.status}
              </p>
            ) : null}
            {item.error && <p className="mt-1 text-sm text-destructive">{item.error}</p>}
            {item.sources.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-primary">
                  {item.sources.length} transcript {item.sources.length === 1 ? "moment" : "moments"} used
                </summary>
                <ul className="mt-1.5 flex flex-col gap-1.5">
                  {item.sources.map((source, index) => (
                    <li key={index}>
                      <button
                        type="button"
                        onClick={() => source.start_time != null && onSeek?.(source.start_time)}
                        className="w-full rounded-md bg-muted px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent-wash"
                      >
                        {source.start_time != null && (
                          <span className="mr-2 font-medium tabular-nums text-primary">
                            {formatClock(source.start_time)}
                          </span>
                        )}
                        {source.content}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </motion.div>
        ))}
      </AnimatePresence>

      <form onSubmit={submit} className="flex flex-col gap-2">
        <Textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask anything about what was said…"
          aria-label="Question about this recording"
          disabled={!hasTranscript}
          maxLength={2000}
          rows={3}
        />
        <Button type="submit" disabled={!hasTranscript || !question.trim()}>
          <Send size={14} /> Ask
        </Button>
      </form>
    </section>
  );
}
