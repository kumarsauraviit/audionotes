# Audio Notes

Upload an audio recording, get a Gnani transcript and a Gemini summary, then ask grounded
questions about that transcript. Built for long, real-world recordings and Indian languages.

## Stack

- `frontend/`: Next.js App Router, TypeScript, **Tailwind CSS v4**, shadcn/ui + Radix,
  TanStack Query, react-hook-form + zod, Sonner, react-dropzone, react-markdown, wavesurfer.js, motion
- `backend/`: FastAPI, SQLAlchemy, PostgreSQL, Celery + Redis
- **Gnani Prisma v2.5** for speech-to-text (Batch, REST, and Timbre TTS)
- Google Gemini via the Google GenAI SDK for summaries, extraction, and a tool-using conversational transcript agent
- Supabase Storage for uploaded audio (private bucket + signed URLs)

## Features

- **Long audio** — Gnani Batch STT, ingested **by reference** from object storage, so there is no
  10 MB upload ceiling and recordings up to 4 hours are supported.
- **Indian languages** — English (India), Hindi, Kannada, Tamil, Telugu, Bengali, Malayalam, Marathi,
  plus automatic English–Hindi detection.
- **Speaker separation** (up to two speakers) with talk-time, and optional **denoising** for noisy audio.
- **Custom vocabulary** — per-user names/brands/jargon boosted in recognition.
- **Timestamped, clickable transcript** — waveform player with click-to-seek; find-in-transcript;
  SRT/VTT, Markdown, and text exports.
- **Summary + structured extraction** — action items, decisions, dates, and entities, plus topic chapters.
- **Read-aloud summaries** — Gnani Timbre TTS generates audio of the summary.
- **Conversational agent** — a Gemini agent with tools to search and navigate the transcript and to read
  the summary and chapters. It answers short recordings straight from the full transcript and pages
  through long ones. Answers cite timestamps that jump the audio and keep multi-turn context.
- **Library** — multi-file upload, tags, filter/search across recordings, and bulk delete.
- **Honest progress and failure** — real stage/percentage/ETA, and a specific reason for every failure.
- **Accounts** — registration, email verification, login with refresh-token rotation, password reset.

## Run locally

1. Copy `backend/.env.example` to `backend/.env` and configure Gnani, Gemini, Supabase, Redis, and auth.
2. Start PostgreSQL and Redis: `docker compose up -d db redis`
3. Install the backend requirements and apply the database migration:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   alembic upgrade head
   ```

4. Start the API:

   ```powershell
   cd backend
   uvicorn app.main:app --reload
   ```

5. In another backend terminal, start the durable background worker:

   ```powershell
   cd backend
   .\.venv\Scripts\Activate.ps1
   celery -A app.queue.celery_app worker --loglevel=info --pool=solo
   ```

6. Start the web app:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`.

## Processing flow

The API validates the upload (default limit `MAX_UPLOAD_MB=200`), probes it with ffmpeg to reject
corrupt audio and read its duration, uploads it to a private Supabase bucket, and stores a
`supabase://bucket/key` reference plus note metadata in PostgreSQL. It then queues a durable Celery job
in Redis and returns `202` immediately.

The worker signs a short-lived URL for the stored object and creates a **Gnani Batch STT** job by
reference (`source.type: "cloud_storage"`), so large files are never re-uploaded through the API. It
starts the job and polls every 10 seconds (the documented minimum), mirroring Gnani's progress counters
back into the note as a real stage/percentage/ETA. Short clips (≤ `GNANI_REST_ITN_MAX_SECONDS`) are sent
to the synchronous REST endpoint instead, which applies inverse text normalization to numbers, currency,
and dates. Speaker separation, denoising, and the user's custom vocabulary are per-job options.

When the job completes, the worker downloads the transcript JSON (full text + timestamped segments),
asks Gemini for a concise summary and for structured extraction (action items, decisions, dates,
entities) plus topic chapters, then keeps the timestamped segments for the agent to search. A summary
that fails marks the note `complete_with_warnings` rather than falsely reporting success. On startup,
notes left mid-flight are re-queued.

The frontend polls the note (via TanStack Query) and shows progress until it is ready. Questions go to a
conversational agent that calls tools to search and navigate the transcript (and to read the summary and
chapters); answers use only tool results and return the matched moments with their audio timestamps so
the UI can jump to the exact moment. Read-aloud summaries are generated on request with Gnani Timbre TTS
and cached in object storage.

## Failure handling

Every failure is stored as a stable `error_code` with a human-readable message and shown in the UI:
corrupt file, no speech detected, unsupported format, storage error, rate-limited/unavailable Gnani,
timeout, rejected job, or a failed summary. Failed notes can be retried.

## API overview

- `POST /api/notes`, `POST /api/notes/bulk` — upload one or many recordings
- `GET /api/notes` (`q`, `status`, `language`, `tag`), `GET /api/notes/{id}`
- `PATCH /api/notes/{id}` (rename), `PATCH /api/notes/{id}/options` (tags, speaker labels)
- `PATCH /api/notes/{id}/transcript` (edit; the agent reads the updated text)
- `GET /api/notes/{id}/audio`, `GET|POST /api/notes/{id}/summary-audio`
- `GET /api/notes/{id}/export?format=txt|md|srt|vtt`
- `POST /api/notes/{id}/ask`, `POST /api/notes/{id}/ask/stream` (SSE), `GET /api/search?q=`
- `GET|PUT /api/settings/glossary`, `GET /api/usage`
- `POST /api/notes/{id}/retry`, `DELETE /api/notes/{id}`, `DELETE /api/notes`
- `POST /api/webhooks/gnani` (optional; polling remains the source of truth)
- `GET /health`

## Authentication

Auth endpoints live under `/api/auth` (register, verify-email, login, refresh, logout, me,
forgot-password, reset-password). Frontend pages: `/login`, `/register`, `/forgot-password`,
`/reset-password`, `/verify-email`. Note and question endpoints require a verified user and are scoped
to the owner. Audio is served through short-lived signed Supabase URLs; the bucket is private by default
(`SUPABASE_BUCKET_PUBLIC=false`).

## Environment variables

See `backend/.env.example` and `frontend/.env.example`. Never commit API keys.

## Tests

Run backend tests from `backend/` with `pytest`. Frontend type-check with `npx tsc --noEmit`.
A GitHub Actions workflow (`.github/workflows/ci.yml`) runs both.

## Deployment

Live (as deployed):

- Frontend: **https://audionotes.vercel.app** (Vercel project `audio-notes`)
- Backend: **https://35.244.57.121.sslip.io** (Compute Engine VM `audionotes-vm`, `asia-south1-a`)

One `e2-medium` VM runs Docker Compose (`deploy/docker-compose.prod.yml`): Caddy (Let's Encrypt TLS) →
FastAPI + Celery worker, with **PostgreSQL and Redis as containers on the VM** (persistent Docker
volumes). Supabase Storage holds the audio objects. The browser talks only to Vercel:
`frontend/next.config.ts` proxies `/api/*` and `/health` to the backend server-side, which removes CORS
and keeps working on networks that block `*.sslip.io`.

Deploy the backend with `deploy/deploy.ps1` (or `deploy/deploy.sh`) and the frontend with
`deploy/deploy-frontend.ps1`. The full runbook is in `deploy/README.md`; a command reference and
deployment gotchas are in `AGENTS.md`. A demo account with seeded meetings is shown on the `/login` and
`/register` pages.
