import {
  API,
  authenticatedFetch,
  getAccessToken,
  getRefreshToken,
  refreshAccessToken,
} from "@/lib/auth";
import type { LibrarySearchHit, Note, SourceChunk } from "@/lib/notes";

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status = 0, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = "Request failed.";
  let code: string | undefined;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((item: { msg: string }) => item.msg).join(" ");
    else if (typeof body.error === "string") detail = body.error;
    code = body.error_code || body.error;
  } catch {
    // ignore non-JSON error bodies
  }
  if (response.status === 401) detail = "Please sign in again to continue.";
  if (response.status === 403) detail = detail || "You don’t have access to this.";
  if (response.status === 404) detail = detail || "Not found.";
  if (response.status === 502 || response.status === 503) {
    detail = detail || "The service is temporarily unavailable. Please try again.";
  }
  return new ApiError(detail, response.status, code);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${API}${path}`, init);
  } catch {
    throw new ApiError("Could not reach the server. Check your connection and try again.", 0);
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --------------------------------------------------------------------------- //
// Notes
// --------------------------------------------------------------------------- //

export type NoteFilters = {
  q?: string;
  status?: string;
  language?: string;
  tag?: string;
};

export async function listNotes(filters: NoteFilters = {}): Promise<Note[]> {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.status) params.set("status", filters.status);
  if (filters.language) params.set("language", filters.language);
  if (filters.tag) params.set("tag", filters.tag);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<Note[]>(`/api/notes${suffix}`, { cache: "no-store" });
}

export async function getNote(id: string): Promise<Note> {
  return request<Note>(`/api/notes/${id}`, { cache: "no-store" });
}

export async function renameNote(id: string, filename: string): Promise<Note> {
  return request<Note>(`/api/notes/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename }),
  });
}

export async function updateNoteOptions(
  id: string,
  payload: { tags?: string[] | null; speaker_labels?: Record<string, string> | null }
): Promise<Note> {
  return request<Note>(`/api/notes/${id}/options`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateTranscript(
  id: string,
  payload: { transcript: string; segments?: unknown[] | null }
): Promise<Note> {
  return request<Note>(`/api/notes/${id}/transcript`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function retryNote(id: string): Promise<Note> {
  return request<Note>(`/api/notes/${id}/retry`, { method: "POST" });
}

export async function deleteNote(id: string): Promise<void> {
  await request(`/api/notes/${id}`, { method: "DELETE" });
}

export type QuestionTurn = { question: string; answer: string };

export async function askQuestion(
  id: string,
  question: string,
  history: QuestionTurn[] = []
): Promise<{ answer: string; sources: unknown[] }> {
  return request(`/api/notes/${id}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
}

export type AskEvent =
  | { type: "tool"; name: string; args?: Record<string, unknown> }
  | { type: "tool_result"; name: string }
  | { type: "sources"; sources: SourceChunk[] }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };

export async function streamQuestion(
  id: string,
  question: string,
  history: QuestionTurn[],
  onEvent: (event: AskEvent) => void
): Promise<void> {
  const response = await authenticatedFetch(`${API}/api/notes/${id}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!response.ok || !response.body) {
    throw new ApiError("Question answering is unavailable right now.", response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((entry) => entry.startsWith("data:"));
      if (!line) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      let parsed: AskEvent | null = null;
      try {
        parsed = JSON.parse(payload) as AskEvent;
      } catch {
        continue;
      }
      if (parsed) onEvent(parsed);
    }
  }
}

export async function searchLibrary(query: string, limit = 8): Promise<{ query: string; hits: LibrarySearchHit[] }> {
  return request(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`, { cache: "no-store" });
}

export async function createSummaryAudio(id: string, voice?: string): Promise<Note> {
  return request<Note>(`/api/notes/${id}/summary-audio`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voice }),
  });
}

export async function getUsage(): Promise<{
  total_notes: number;
  total_audio_minutes: number;
  stt_estimate_inr: number;
  tts_estimate_inr: number;
  credits_estimate_inr: number;
}> {
  return request(`/api/usage`, { cache: "no-store" });
}

// --------------------------------------------------------------------------- //
// Glossary
// --------------------------------------------------------------------------- //

export type Glossary = { glossary: string[]; default_language: string | null };

export async function getGlossary(): Promise<Glossary> {
  return request(`/api/settings/glossary`, { cache: "no-store" });
}

export async function updateGlossary(glossary: string[], defaultLanguage?: string): Promise<Glossary> {
  return request(`/api/settings/glossary`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ glossary, default_language: defaultLanguage ?? null }),
  });
}

// --------------------------------------------------------------------------- //
// Uploads (XHR so we can show real byte progress)
// --------------------------------------------------------------------------- //

export type UploadInput = {
  file: File;
  languageCode: string;
  withDiarization: boolean;
  withDenoise: boolean;
  tags?: string;
  allowLossy?: boolean;
  onProgress?: (percent: number) => void;
};

export async function uploadNote(input: UploadInput): Promise<Note> {
  const form = new FormData();
  form.append("audio", input.file, input.file.name);
  form.append("language_code", input.languageCode);
  form.append("with_diarization", String(input.withDiarization));
  form.append("with_denoise", String(input.withDenoise));
  form.append("allow_lossy_compression", String(input.allowLossy ?? false));
  if (input.tags) form.append("tags", input.tags);

  const send = (token: string | null) =>
    new Promise<{ status: number; text: string }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API}/api/notes`);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && input.onProgress) {
          input.onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
      xhr.onload = () => resolve({ status: xhr.status, text: xhr.responseText });
      xhr.onerror = () => reject(new ApiError("Upload failed. Check your connection and try again.", 0));
      xhr.send(form);
    });

  let result = await send(getAccessToken());
  if (result.status === 401 && getRefreshToken()) {
    const token = await refreshAccessToken();
    if (token) result = await send(token);
  }
  if (result.status < 200 || result.status >= 300) {
    let detail = "Upload failed. Please try again.";
    try {
      const body = JSON.parse(result.text);
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, result.status);
  }
  return JSON.parse(result.text) as Note;
}

// Authenticated media/export URLs. The token is appended because <audio> and
// downloads can't send an Authorization header.
export function audioUrl(note: Note): string {
  const token = getAccessToken();
  return `${API}/api/notes/${note.id}/audio${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

export function summaryAudioUrl(note: Note): string {
  const token = getAccessToken();
  return `${API}/api/notes/${note.id}/summary-audio${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

export function exportUrl(note: Note, format: "txt" | "md" | "srt" | "vtt"): string {
  const token = getAccessToken();
  return `${API}/api/notes/${note.id}/export?format=${format}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
}
