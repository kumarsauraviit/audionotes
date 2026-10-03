"use client";

import { useEffect, useState } from "react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { TagEditor } from "./TagEditor";
import { useUpdateNoteOptions } from "@/hooks/useNotes";
import type { Note } from "@/lib/notes";

export function TagDialog({
  note,
  open,
  onOpenChange,
}: {
  note: Note | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const update = useUpdateNoteOptions();
  const [tags, setTags] = useState<string[]>([]);

  useEffect(() => {
    setTags(note?.tags ?? []);
  }, [note, open]);

  if (!note) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit tags</DialogTitle>
          <DialogDescription className="truncate">{note.filename}</DialogDescription>
        </DialogHeader>
        <TagEditor tags={tags} onChange={setTags} disabled={update.isPending} />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={async () => {
              await update.mutateAsync({ id: note.id, tags });
              onOpenChange(false);
            }}
            disabled={update.isPending}
          >
            Save tags
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
