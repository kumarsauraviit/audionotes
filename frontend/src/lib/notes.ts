export type Segment = {
  start_time: number;
  end_time: number;
  text: string;
  speaker_id?: number | null;
  confidence?: number | null;
};

export type SourceChunk = {
  chunk_index: number;
  content: string;
  score: number | null;
  start_time?: number | null;
  end_time?: number | null;
};

export type Extraction = {
  action_items: string[];
  decisions: string[];
  dates: string[];
  entities: Record<string, string[]>;
  questions: string[];
};

export type Chapter = {
  title: string;
  start_time: number;
  end_time: number;
  summary?: string | null;
};

export type SummaryStatus = "pending" | "ready" | "failed" | "skipped";

export type NoteStatus =
  | "queued"
  | "transcribing"
  | "summarizing"
  | "indexing"
  | "complete"
  | "complete_with_warnings"
  | "failed";

export type Note = {
  id: string;
  filename: string;
  file_size: number;
  language_code: string;
  detected_language?: string | null;
  duration_seconds?: number | null;
  status: NoteStatus;
  transcript: string | null;
  summary: string | null;
  summary_status?: SummaryStatus;
  segments?: Segment[] | null;
  extraction?: Extraction | null;
  chapters?: Chapter[] | null;
  speaker_labels?: Record<string, string> | null;
  tags?: string[] | null;
  transcription_engine?: string | null;
  summary_model?: string | null;
  stage?: string | null;
  progress_percent?: number | null;
  progress_message?: string | null;
  eta_seconds?: number | null;
  gnani_status?: string | null;
  with_diarization?: boolean;
  with_denoise?: boolean;
  error_code?: string | null;
  error_message: string | null;
  retry_count?: number;
  has_summary_audio?: boolean;
  summary_audio_voice?: string | null;
  created_at: string;
  updated_at?: string;
};

export type LibrarySearchHit = {
  note_id: string;
  filename: string;
  chunk_index: number;
  content: string;
  score: number | null;
  start_time?: number | null;
  end_time?: number | null;
};

export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 200);
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
export const GNANI_MAX_BYTES = 9_500 * 1024;

export const LANGUAGES = [
  { code: "en-IN", label: "English (India)" },
  { code: "en-IN,hi-IN", label: "Auto-detect (English & Hindi)" },
  { code: "hi-IN", label: "Hindi" },
  { code: "kn-IN", label: "Kannada" },
  { code: "ta-IN", label: "Tamil" },
  { code: "te-IN", label: "Telugu" },
  { code: "bn-IN", label: "Bengali" },
  { code: "ml-IN", label: "Malayalam" },
  { code: "mr-IN", label: "Marathi" },
];

export const PHASES = ["queued", "transcribing", "summarizing", "indexing", "complete"] as const;

export const STAGE_LABELS: Record<string, string> = {
  queued: "In queue",
  preparing: "Preparing",
  transcribing: "Transcribing",
  summarizing: "Summarizing",
  indexing: "Indexing",
  complete: "Ready",
  failed: "Failed",
};

export const STAGE_COPY: Record<string, string> = {
  queued: "Getting your audio ready",
  preparing: "Getting your audio ready",
  transcribing: "Listening to every word",
  summarizing: "Finding the important bits",
  indexing: "Making it searchable",
};

// Mirrors backend app/errors.py so the UI can show specific, honest failures.
export const ERROR_COPY: Record<string, string> = {
  unsupported_format: "That audio format isn’t supported. Try WAV, MP3, M4A, MP4, FLAC, OGG, OPUS, AAC, WEBM, or AMR.",
  empty_file: "The audio file was empty.",
  file_too_large: "This recording is too large to process. Try splitting it.",
  corrupt_audio: "This audio file appears to be corrupted or unreadable.",
  silent_audio: "This recording looks silent — we couldn’t find any speech in it.",
  no_speech: "We couldn’t detect any speech in this recording.",
  storage_error: "We couldn’t store or read the audio file. Please try again.",
  compression_failed: "We couldn’t prepare this audio for transcription.",
  gnani_auth: "The transcription service rejected our credentials. Please try again later.",
  gnani_rate_limit: "The transcription service was busy. Retry in a moment.",
  gnani_timeout: "Transcription took too long and timed out. You can retry it.",
  gnani_unavailable: "The transcription service was temporarily unavailable. Please retry.",
  gnani_rejected: "The transcription service couldn’t process this audio.",
  summary_failed: "The transcript is ready, but the summary failed.",
  internal_error: "Something went wrong while processing this recording.",
};

export function errorCopy(code?: string | null, fallback?: string | null) {
  if (code && ERROR_COPY[code]) return ERROR_COPY[code];
  return fallback || "Something went wrong during processing.";
}

export function isProcessingStatus(status: NoteStatus) {
  return ["queued", "transcribing", "summarizing", "indexing"].includes(status);
}

export function languageLabel(code: string) {
  const exact = LANGUAGES.find((item) => item.code === code);
  if (exact) return exact.label;
  const first = code.split(",")[0];
  return LANGUAGES.find((item) => item.code === first)?.label ?? code;
}

export function statusLabel(status: NoteStatus) {
  switch (status) {
    case "complete":
      return "Ready";
    case "complete_with_warnings":
      return "Ready (with warnings)";
    case "failed":
      return "Failed";
    case "queued":
      return "Queued";
    case "transcribing":
      return "Transcribing";
    case "indexing":
      return "Indexing";
    default:
      return "Summarizing";
  }
}

export function prettySize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(0)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function prettyDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatClock(secs: number) {
  if (!Number.isFinite(secs) || secs < 0) return "0:00";
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

export function formatDuration(secs: number) {
  if (!Number.isFinite(secs) || secs <= 0) return "—";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function stripExtension(name: string) {
  return name.replace(/\.[^./\\]+$/, "") || name;
}

export function countMatches(text: string, query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  let count = 0;
  let index = text.toLowerCase().indexOf(q);
  while (index !== -1) {
    count += 1;
    index = text.toLowerCase().indexOf(q, index + q.length);
  }
  return count;
}
