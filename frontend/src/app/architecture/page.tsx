import Link from "next/link";
import {
  ArrowLeft,
  Cloud,
  Database,
  FileAudio2,
  FileText,
  Layers3,
  Mic2,
  Search,
  Sparkles,
  Timer,
  Waypoints,
} from "lucide-react";

import { Brand } from "@/components/Brand";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

const repoUrl =
  process.env.NEXT_PUBLIC_GITHUB_REPO_URL || "https://github.com/your-username/audio-notes";

const flow = [
  {
    icon: FileAudio2,
    title: "Upload & validate",
    body: "The signed-in user selects a language and one or more audio files. FastAPI probes each file with ffmpeg to reject corrupt audio immediately and to learn its duration. Audio is stored in Supabase Storage and a note row is written to PostgreSQL.",
  },
  {
    icon: Layers3,
    title: "Queue background work",
    body: "FastAPI enqueues the note id in Redis via Celery and returns 202 immediately. Nothing slow happens in the request. The UI polls the note and shows a real stage, percentage, and estimated time remaining.",
  },
  {
    icon: Mic2,
    title: "Transcribe with Gnani",
    body: "The Celery worker signs a short-lived URL for the stored audio and creates a Gnani Batch STT job by reference. It starts the job and polls every 10 seconds, mirroring Gnani's own progress counters back into the note.",
  },
  {
    icon: Sparkles,
    title: "Summarize & extract",
    body: "Gemini writes the summary and pulls out action items, decisions, dates, and entities. The timestamped transcript is kept so the agent can search and navigate it.",
  },
  {
    icon: Search,
    title: "Ask about it",
    body: "A conversational agent answers questions by calling tools that search and navigate the transcript and read the summary or chapters. It answers only from what the tools return, and every referenced moment links back to its timestamp in the audio.",
  },
];

export default function ArchitecturePage() {
  return (
    <main className="mx-auto max-w-4xl px-5 py-8 sm:px-8">
      <nav className="mb-8 flex items-center justify-between">
        <Brand />
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary">
          <ArrowLeft size={16} /> Back to library
        </Link>
      </nav>

      <header className="mb-8">
        <span className="text-xs font-semibold uppercase tracking-wide text-primary">Under the hood</span>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          From recording to clarity
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          How Audio Notes stores, processes, and answers questions about your recordings.
        </p>
      </header>

      <section className="mb-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">The flow, upload → transcript</h2>
          <Badge variant="secondary">Async after upload</Badge>
        </div>
        <ol className="flex flex-col gap-3">
          {flow.map((step, index) => (
            <li key={step.title}>
              <Card>
                <CardContent className="flex gap-4 p-4">
                  <span className="grid size-9 shrink-0 place-items-center rounded-md bg-accent-wash text-accent">
                    <step.icon size={18} />
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold">
                      <span className="mr-2 tabular-nums text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
                      {step.title}
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">{step.body}</p>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      <section className="mb-10 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Cloud size={16} className="text-accent" /> Where files live
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Audio lives in a private Supabase Storage bucket. The database stores a
            <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">supabase://bucket/key</code>
            reference, never a public URL. Playback and Gnani access are handed short-lived signed URLs.
            PostgreSQL stores notes, transcripts, summaries, options, and progress.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Database size={16} className="text-accent" /> Derived data
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Redis carries the Celery queue. Transcript segments are stored with their timestamps, and the
            conversational agent uses tools to search and read them directly — no embeddings or vector store
            to keep in sync, and every citation traces back to a moment in the audio.
          </CardContent>
        </Card>
      </section>

      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">Long audio</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardContent className="p-4 text-sm text-muted-foreground">
              <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
                <Timer size={15} className="text-accent" /> Up to 4 hours
              </div>
              We use Gnani&apos;s <strong>Batch</strong> API, not the 60-second REST endpoint, and we send
              audio <strong>by reference</strong> from object storage — so there is no 10 MB per-file upload
              ceiling.
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-sm text-muted-foreground">
              <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
                <Waypoints size={15} className="text-accent" /> No frozen page
              </div>
              Progress is driven by Gnani&apos;s own job counters plus the audio duration, so a long file
              shows an advancing bar, a stage, and an estimated time remaining instead of a spinner.
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-sm text-muted-foreground">
              <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
                <Mic2 size={15} className="text-accent" /> Optional &amp; tunable
              </div>
              Two-speaker separation, denoising for noisy recordings, and a custom vocabulary are per-job
              options, so we only pay for the processing a recording actually needs.
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">What runs synchronously vs in the background</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Synchronous (inside the request)</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">
                <li>Format and size validation, plus an ffmpeg probe</li>
                <li>Upload to object storage</li>
                <li>Writing the note row</li>
                <li>Enqueuing the background job</li>
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Background (Celery worker)</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">
                <li>Creating and starting the Gnani job</li>
                <li>Polling until completion and downloading the transcript</li>
                <li>Summary, extraction, and chapter generation</li>
                <li>Chunking, embedding, and indexing</li>
                <li>Read-aloud summary audio on request</li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-semibold">Handling failure</h2>
        <p className="text-sm text-muted-foreground">
          Every failure maps to a specific, human-readable cause stored on the note and shown in the UI:
          corrupt file, no speech detected, unsupported format, rate-limited or unavailable transcription
          service, timeout, storage error, or a failed summary. A job that was interrupted mid-flight is
          re-queued on startup. Failures offer a one-click retry.
        </p>
      </section>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-semibold">What I&apos;d do differently with more time</h2>
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
          <li><strong>Webhooks over polling.</strong> Gnani can POST finished jobs to us; polling is the fallback, but events would cut latency and work.</li>
          <li><strong>A lightweight inverted index per recording</strong> so transcript search stays fast even at the four-hour limit.</li>
          <li><strong>Let the agent quote exact lines</strong> and highlight the matched phrase inline in the transcript.</li>
          <li><strong>Streaming answers</strong> so questions feel incremental rather than one long wait.</li>
          <li><strong>Per-speaker summaries and speaker relabelling</strong> once diarization is on.</li>
          <li><strong>A real credit meter</strong> derived from actual Gnani billing rather than an estimate.</li>
          <li><strong>Object lifecycle rules</strong> to expire audio separately from transcripts.</li>
        </ul>
      </section>

      <Separator />

      <footer className="mt-6 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
        <span>Built with Next.js, FastAPI, Gnani, Gemini, Supabase, Redis, and Celery.</span>
        <a href={repoUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
          <FileText size={14} /> View the GitHub repository
        </a>
      </footer>
    </main>
  );
}
