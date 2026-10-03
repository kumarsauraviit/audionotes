"use client";

import { useEffect, useState } from "react";
import { BookText, Plus, X } from "lucide-react";

import { useWorkspace } from "./WorkspaceProvider";
import { useGlossary, useUpdateGlossary } from "@/hooks/useNotes";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LANGUAGES } from "@/lib/notes";

export function GlossaryDialog() {
  const { glossaryOpen, closeGlossary } = useWorkspace();
  const { data, isLoading } = useGlossary();
  const updateGlossary = useUpdateGlossary();
  const [words, setWords] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [language, setLanguage] = useState<string>("en-IN");
  const [error, setError] = useState("");

  useEffect(() => {
    if (data) {
      setWords(data.glossary ?? []);
      setLanguage(data.default_language ?? "en-IN");
    }
  }, [data, glossaryOpen]);

  const addWord = () => {
    const token = draft.trim();
    if (!token) return;
    if (!/^[A-Za-z\u0900-\u097F\u0C00-\u0C7F\u0B80-\u0BFF\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF\u0A00-\u0A7F]+$/u.test(token)) {
      setError("Use a single word of letters only (no spaces, digits, or punctuation).");
      return;
    }
    if (words.includes(token)) {
      setError("That word is already in your glossary.");
      return;
    }
    if (words.length >= 100) {
      setError("You can save up to 100 words.");
      return;
    }
    setWords((current) => [...current, token]);
    setDraft("");
    setError("");
  };

  const removeWord = (word: string) => setWords((current) => current.filter((item) => item !== word));

  const save = () => {
    updateGlossary.mutate(
      { glossary: words, defaultLanguage: language },
      { onSuccess: () => closeGlossary() }
    );
  };

  return (
    <Dialog open={glossaryOpen} onOpenChange={(open) => !open && closeGlossary()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-md bg-accent-wash text-accent">
              <BookText size={18} />
            </span>
            Custom vocabulary
          </DialogTitle>
          <DialogDescription>
            Names, brands, and jargon to recognise. These are applied to every new recording.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addWord();
              }
            }}
            placeholder="e.g. Gnani, Karnataka, EMI"
            aria-label="Add a vocabulary word"
          />
          <Button type="button" variant="outline" onClick={addWord}>
            <Plus size={15} /> Add
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex max-h-56 flex-wrap gap-2 overflow-auto">
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {!isLoading && words.length === 0 && (
            <p className="text-sm text-muted-foreground">No words yet. Add a few to improve recognition.</p>
          )}
          {words.map((word) => (
            <span key={word} className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-sm text-secondary-foreground">
              {word}
              <button
                type="button"
                onClick={() => removeWord(word)}
                className="rounded-full p-0.5 hover:bg-accent-wash"
                aria-label={`Remove ${word}`}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>

        <div className="grid grid-cols-[1fr_auto] items-center gap-3">
          <Label>Default language for new recordings</Label>
          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger className="w-52">
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

        <Button onClick={save} disabled={updateGlossary.isPending}>
          {updateGlossary.isPending ? "Saving…" : "Save glossary"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
