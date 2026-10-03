"use client";

import Link from "next/link";
import { CircleHelp } from "lucide-react";

import { useWorkspace } from "./WorkspaceProvider";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const guide = [
  { title: "Add a recording", body: "Drop in one or many audio files, pick the spoken language, and optionally turn on speaker separation or noise cleanup." },
  { title: "We transcribe with Gnani", body: "Long recordings are sent to Gnani’s Batch speech-to-text service, which handles files up to four hours." },
  { title: "Read, hear, and verify", body: "Get a timestamped transcript, a summary, and a read-aloud version of the summary. Click any line to jump the audio there." },
  { title: "Find and ask", body: "Search inside a transcript or across your whole library, and ask questions that are answered only from the recording — with the excerpts shown." },
  { title: "Export what you need", body: "Download the transcript as text, Markdown, or SRT/VTT subtitles." },
];

const features = [
  { badge: "Languages", title: "Built for Indian languages", body: "English, Hindi, Kannada, Tamil, Telugu, Bengali, Malayalam, and Marathi, with automatic English–Hindi detection." },
  { badge: "Speakers", title: "Who said what", body: "Turn on speaker separation for interviews and calls to see labels and talk time." },
  { badge: "Vocabulary", title: "Your names, spelled right", body: "Add brands, names, and jargon to your custom vocabulary so they are recognised correctly." },
  { badge: "Summary", title: "A short read of a long recording", body: "Every recording gets a concise overview, plus action items, decisions, and dates pulled out." },
  { badge: "Answers", title: "Ask, with the evidence shown", body: "Answers cite the exact transcript moment and can jump the audio to it." },
  { badge: "Progress", title: "Honest progress", body: "A clear stage-by-stage view with an estimated time remaining, and a specific reason if something fails." },
];

export function HelpDialog() {
  const { helpOpen, closeHelp } = useWorkspace();

  return (
    <Dialog open={helpOpen} onOpenChange={(open) => !open && closeHelp()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-md bg-accent-wash text-accent">
              <CircleHelp size={18} />
            </span>
            How Audio Notes works
          </DialogTitle>
          <DialogDescription>Recordings in. Transcripts, summaries, and answers out.</DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="guide">
          <TabsList>
            <TabsTrigger value="guide">Getting started</TabsTrigger>
            <TabsTrigger value="features">What you can do</TabsTrigger>
          </TabsList>
          <TabsContent value="guide">
            <div className="grid gap-3 sm:grid-cols-2">
              {guide.map((step, index) => (
                <div key={step.title} className="rounded-lg border border-border p-4">
                  <span className="text-xs font-semibold tabular-nums text-muted-foreground">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-1 text-sm font-semibold">{step.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{step.body}</p>
                </div>
              ))}
            </div>
          </TabsContent>
          <TabsContent value="features">
            <div className="grid gap-3 sm:grid-cols-2">
              {features.map((feature) => (
                <div key={feature.title} className="rounded-lg border border-border p-4">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-primary">{feature.badge}</span>
                  <h4 className="mt-1 text-sm font-semibold">{feature.title}</h4>
                  <p className="mt-1 text-sm text-muted-foreground">{feature.body}</p>
                </div>
              ))}
            </div>
          </TabsContent>
        </Tabs>

        <div className="flex items-center justify-between border-t border-border pt-4">
          <Link href="/architecture" className="text-sm text-primary underline-offset-4 hover:underline" onClick={closeHelp}>
            How processing works
          </Link>
        </div>
      </DialogContent>
    </Dialog>
  );
}
