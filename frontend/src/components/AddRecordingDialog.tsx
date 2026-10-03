"use client";

import { useCallback, useEffect, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileAudio2, LoaderCircle, ShieldCheck, UploadCloud, X } from "lucide-react";

import { useAuth } from "@/context/AuthContext";
import { useWorkspace } from "./WorkspaceProvider";
import { ApiError, uploadNote } from "@/lib/api";
import {
  GNANI_MAX_BYTES,
  LANGUAGES,
  MAX_UPLOAD_MB,
  prettySize,
} from "@/lib/notes";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const ACCEPT = {
  "audio/*": [".wav", ".mp3", ".mp4", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".amr"],
};

const schema = z.object({
  languageCode: z.string().min(1),
  tags: z.string().optional(),
  withDiarization: z.boolean(),
  withDenoise: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

type UploadState = { name: string; percent: number };

export function AddRecordingDialog() {
  const { isAuthenticated, user } = useAuth();
  const { addOpen, closeAdd } = useWorkspace();
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [error, setError] = useState("");

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { languageCode: "en-IN", tags: "", withDiarization: false, withDenoise: false },
  });

  useEffect(() => {
    if (!addOpen) {
      setFiles([]);
      setUploads([]);
      setError("");
      setBusy(false);
    }
  }, [addOpen]);

  const onDrop = useCallback((accepted: File[], rejections: FileRejection[]) => {
    setError("");
    const tooBig = accepted.filter((file) => file.size > MAX_UPLOAD_MB * 1024 * 1024);
    const ok = accepted.filter((file) => file.size <= MAX_UPLOAD_MB * 1024 * 1024);
    if (tooBig.length) setError(`Some files are larger than ${MAX_UPLOAD_MB} MB and were skipped.`);
    if (rejections.length) setError("Some files were not audio and were skipped.");
    setFiles((current) => [...current, ...ok].slice(0, 20));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    multiple: true,
    disabled: busy,
  });

  const removeFile = (index: number) => setFiles((current) => current.filter((_, i) => i !== index));

  const verified = isAuthenticated && (!user || user.is_verified);

  const submit = form.handleSubmit(async (values) => {
    if (!files.length || busy) return;
    setBusy(true);
    setError("");
    const states = files.map((file) => ({ name: file.name, percent: 0 }));
    setUploads(states);
    let failures = 0;
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      try {
        await uploadNote({
          file,
          languageCode: values.languageCode,
          withDiarization: values.withDiarization,
          withDenoise: values.withDenoise,
          tags: values.tags,
          allowLossy: file.size > GNANI_MAX_BYTES,
          onProgress: (percent) =>
            setUploads((current) => current.map((item, i) => (i === index ? { ...item, percent } : item))),
        });
      } catch (reason) {
        failures += 1;
        const message = reason instanceof ApiError ? reason.message : "Upload failed.";
        setError(`${file.name}: ${message}`);
      }
    }
    setBusy(false);
    await queryClient.invalidateQueries({ queryKey: ["notes"] });
    await queryClient.invalidateQueries({ queryKey: ["usage"] });
    if (failures === 0) {
      toast.success(files.length > 1 ? `${files.length} recordings added.` : "Recording added. We’ll mark it ready when it’s done.");
      closeAdd();
    } else if (failures < files.length) {
      toast.warning("Some recordings were added, some failed.");
    }
  });

  return (
    <Dialog open={addOpen} onOpenChange={(open) => !open && closeAdd()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-md bg-accent-wash text-accent">
              <UploadCloud size={18} />
            </span>
            Add recordings
          </DialogTitle>
          <DialogDescription>
            Drop audio in and we’ll transcribe, summarize, and let you ask questions.
          </DialogDescription>
        </DialogHeader>

        <div
          {...getRootProps()}
          className={cn(
            "flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center transition-colors",
            isDragActive ? "border-primary bg-accent-wash" : "border-line bg-canvas hover:border-primary/60"
          )}
        >
          <input {...getInputProps()} />
          <span className="mb-3 grid size-11 place-items-center rounded-xl bg-accent-wash text-accent">
            <UploadCloud size={22} />
          </span>
          <span className="text-sm font-semibold">Drop your audio here</span>
          <span className="mt-1 text-xs text-muted-foreground">
            or click to browse · up to {MAX_UPLOAD_MB} MB each · WAV, MP3, M4A, and 7 more
          </span>
        </div>

        {files.length > 0 && (
          <ul className="flex max-h-40 flex-col gap-1.5 overflow-auto">
            {files.map((file, index) => {
              const progress = uploads[index];
              return (
                <li key={`${file.name}-${index}`} className="flex items-center gap-3 rounded-md border border-border px-3 py-2">
                  <FileAudio2 size={16} className="shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{file.name}</p>
                    {progress ? (
                      <div className="mt-1 flex items-center gap-2">
                        <Progress value={progress.percent} className="h-1.5" />
                        <span className="w-9 text-right text-[11px] tabular-nums text-muted-foreground">
                          {progress.percent}%
                        </span>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">{prettySize(file.size)}</p>
                    )}
                  </div>
                  {!busy && (
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-ink"
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={14} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <div className="grid gap-3">
          <div className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div>
              <Label htmlFor="add-language">Spoken language</Label>
              <p className="text-xs text-muted-foreground">Choose the language so the transcript is accurate.</p>
            </div>
            <Select value={form.watch("languageCode")} onValueChange={(value) => form.setValue("languageCode", value)}>
              <SelectTrigger id="add-language" className="w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANGUAGES.map((item) => (
                  <SelectItem key={item.code} value={item.code}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div>
              <Label htmlFor="add-tags">Tags</Label>
              <p className="text-xs text-muted-foreground">Comma separated, optional.</p>
            </div>
            <Input id="add-tags" className="w-52" placeholder="meeting, client" {...form.register("tags")} />
          </div>

          <div className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div>
              <Label>Identify speakers</Label>
              <p className="text-xs text-muted-foreground">Separates up to two speakers (interviews, calls).</p>
            </div>
            <Switch
              checked={form.watch("withDiarization")}
              onCheckedChange={(checked) => form.setValue("withDiarization", checked)}
            />
          </div>

          <div className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div>
              <Label>Clean up noise</Label>
              <p className="text-xs text-muted-foreground">Enable for noisy recordings; adds processing time.</p>
            </div>
            <Switch
              checked={form.watch("withDenoise")}
              onCheckedChange={(checked) => form.setValue("withDenoise", checked)}
            />
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
            <X size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!isAuthenticated ? (
          <Button asChild className="w-full">
            <a href="/login">Log in to add a recording</a>
          </Button>
        ) : user && !user.is_verified ? (
          <Button asChild className="w-full">
            <a href="/verify-email">
              <ShieldCheck size={15} /> Verify your email to add recordings
            </a>
          </Button>
        ) : (
          <Button className="w-full" onClick={() => void submit()} disabled={!files.length || busy}>
            {busy ? (
              <>
                <LoaderCircle size={16} className="animate-spin" /> Uploading…
              </>
            ) : files.length > 1 ? (
              `Add ${files.length} recordings`
            ) : (
              "Add recording"
            )}
          </Button>
        )}
      </DialogContent>
    </Dialog>
  );
}
