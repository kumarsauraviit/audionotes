"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { AddRecordingDialog } from "./AddRecordingDialog";
import { HelpDialog } from "./HelpDialog";
import { GlossaryDialog } from "./GlossaryDialog";

type ToastTone = "success" | "error";

type WorkspaceContextType = {
  addOpen: boolean;
  openAdd: () => void;
  closeAdd: () => void;
  helpOpen: boolean;
  openHelp: () => void;
  closeHelp: () => void;
  glossaryOpen: boolean;
  openGlossary: () => void;
  closeGlossary: () => void;
  showToast: (message: string, tone?: ToastTone) => void;
};

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

/**
 * UI-only shell state: which global dialog is open, plus a toast bridge kept for
 * components that predate the shadcn rewrite. Server state now lives in
 * react-query (see `hooks/useNotes.ts`).
 */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [addOpen, setAddOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [glossaryOpen, setGlossaryOpen] = useState(false);

  const showToast = useCallback((message: string, tone: ToastTone = "success") => {
    if (tone === "error") toast.error(message);
    else toast.success(message);
  }, []);

  const value = useMemo<WorkspaceContextType>(
    () => ({
      addOpen,
      openAdd: () => setAddOpen(true),
      closeAdd: () => setAddOpen(false),
      helpOpen,
      openHelp: () => setHelpOpen(true),
      closeHelp: () => setHelpOpen(false),
      glossaryOpen,
      openGlossary: () => setGlossaryOpen(true),
      closeGlossary: () => setGlossaryOpen(false),
      showToast,
    }),
    [addOpen, helpOpen, glossaryOpen, showToast]
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
      <AddRecordingDialog />
      <HelpDialog />
      <GlossaryDialog />
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("useWorkspace must be used within a WorkspaceProvider");
  return context;
}
