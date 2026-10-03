"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  askQuestion,
  createSummaryAudio,
  deleteNote,
  getGlossary,
  getNote,
  getUsage,
  listNotes,
  renameNote,
  retryNote,
  searchLibrary,
  updateGlossary,
  updateNoteOptions,
  updateTranscript,
  type NoteFilters,
  type QuestionTurn,
} from "@/lib/api";
import { isProcessingStatus, type Note } from "@/lib/notes";
import { toast } from "sonner";

export const notesKey = (filters: NoteFilters) => ["notes", filters] as const;
export const noteKey = (id: string) => ["note", id] as const;

const pollWhileProcessing = (data: Note[] | Note | undefined) => {
  const list = Array.isArray(data) ? data : data ? [data] : [];
  return list.some((note) => isProcessingStatus(note.status)) ? 3000 : false;
};

export function useNotes(filters: NoteFilters = {}) {
  return useQuery({
    queryKey: notesKey(filters),
    queryFn: () => listNotes(filters),
    refetchInterval: (query) => pollWhileProcessing(query.state.data as Note[] | undefined),
    staleTime: 1000,
  });
}

export function useNote(id: string, enabled = true) {
  return useQuery({
    queryKey: noteKey(id),
    queryFn: () => getNote(id),
    enabled: Boolean(id) && enabled,
    refetchInterval: (query) => pollWhileProcessing(query.state.data as Note | undefined),
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["notes"] });
    void queryClient.invalidateQueries({ queryKey: ["note"] });
  };
}

export function useRenameNote() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, filename }: { id: string; filename: string }) => renameNote(id, filename),
    onSuccess: () => {
      invalidate();
      toast.success("Recording renamed.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDeleteNote() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => deleteNote(id),
    onSuccess: () => {
      invalidate();
      toast.success("Recording deleted.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRetryNote() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => retryNote(id),
    onSuccess: () => {
      invalidate();
      toast.success("Retrying this recording.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateNoteOptions() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({
      id,
      tags,
      speaker_labels,
    }: {
      id: string;
      tags?: string[] | null;
      speaker_labels?: Record<string, string> | null;
    }) => updateNoteOptions(id, { tags, speaker_labels }),
    onSuccess: () => invalidate(),
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateTranscript() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, transcript, segments }: { id: string; transcript: string; segments?: unknown[] | null }) =>
      updateTranscript(id, { transcript, segments }),
    onSuccess: () => {
      invalidate();
      toast.success("Transcript updated and re-indexed.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useAsk(noteId: string) {
  return useMutation({
    mutationFn: ({ question, history = [] }: { question: string; history?: QuestionTurn[] }) =>
      askQuestion(noteId, question, history),
  });
}

export function useSummaryAudio(noteId: string) {
  const invalidate = useInvalidate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (voice?: string) => createSummaryAudio(noteId, voice),
    onSuccess: (note) => {
      // The generation response already contains the persisted audio ref. Show
      // the player immediately instead of waiting for the detail refetch.
      queryClient.setQueryData(noteKey(noteId), note);
      invalidate();
      toast.success("Summary audio is ready.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useLibrarySearch(query: string) {
  return useQuery({
    queryKey: ["library-search", query],
    queryFn: () => searchLibrary(query),
    enabled: query.trim().length >= 3,
    staleTime: 30_000,
  });
}

export function useGlossary() {
  return useQuery({ queryKey: ["glossary"], queryFn: getGlossary, staleTime: 60_000 });
}

export function useUpdateGlossary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ glossary, defaultLanguage }: { glossary: string[]; defaultLanguage?: string }) =>
      updateGlossary(glossary, defaultLanguage),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glossary"] });
      toast.success("Glossary saved.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUsage() {
  return useQuery({ queryKey: ["usage"], queryFn: getUsage, staleTime: 30_000 });
}
