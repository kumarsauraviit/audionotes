"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function TagEditor({
  tags,
  onChange,
  disabled,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const tag = draft.trim().replace(/^#/, "");
    if (!tag) return;
    if (!tags.includes(tag)) onChange([...tags, tag].slice(0, 20));
    setDraft("");
  };

  const remove = (tag: string) => onChange(tags.filter((item) => item !== tag));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs text-secondary-foreground"
          >
            #{tag}
            <button
              type="button"
              onClick={() => remove(tag)}
              disabled={disabled}
              className="rounded-full p-0.5 transition-colors hover:bg-accent-wash disabled:opacity-50"
              aria-label={`Remove tag ${tag}`}
            >
              <X size={11} />
            </button>
          </span>
        ))}
        {tags.length === 0 && <span className="text-xs text-muted-foreground">No tags yet.</span>}
      </div>
      <div className="flex gap-1.5">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          placeholder="Add a tag"
          className="h-8 text-xs"
          disabled={disabled}
          aria-label="Add a tag"
        />
        <Button type="button" size="sm" variant="outline" onClick={add} disabled={disabled}>
          <Plus size={13} /> Add
        </Button>
      </div>
    </div>
  );
}
