"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenText, BookText, ChevronRight, CircleHelp, Plus } from "lucide-react";

import { AuthNav } from "./AuthNav";
import { Brand } from "./Brand";
import { useWorkspace } from "./WorkspaceProvider";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function AppShell({ center, children }: { center?: ReactNode; children: ReactNode }) {
  const { openHelp, openGlossary } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="sticky top-0 z-40 border-b border-border bg-paper/90 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-[1500px] items-center gap-3 px-5 sm:px-8">
          <Brand />
          {center ? (
            <>
              <Separator orientation="vertical" className="h-6" />
              <div className="flex min-w-0 flex-1 items-center">{center}</div>
            </>
          ) : (
            <div className="flex-1" />
          )}
          <div className="flex shrink-0 items-center gap-1.5">
            <AddButton />
            <IconButton label="Custom vocabulary" onClick={openGlossary}>
              <BookText size={17} />
            </IconButton>
            <IconButton label="How it works" onClick={openHelp}>
              <CircleHelp size={17} />
            </IconButton>
            <AuthNav />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1500px] flex-1 px-5 pb-24 pt-7 sm:px-8 md:pb-10">{children}</main>
      <MobileTabBar />
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={onClick} aria-label={label}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function AddButton() {
  const { openAdd } = useWorkspace();
  return (
    <Button onClick={openAdd} size="sm" className="h-9">
      <Plus size={16} />
      <span className="hidden sm:inline">Add recording</span>
    </Button>
  );
}

/** Consistent breadcrumb used in the top bar. */
export function TopBreadcrumb({ current }: { current: string }) {
  return (
    <nav className="flex min-w-0 items-center gap-1.5 text-sm" aria-label="Breadcrumb">
      <Link href="/" className="shrink-0 text-muted-foreground transition-colors hover:text-primary">
        Library
      </Link>
      <ChevronRight size={14} className="shrink-0 text-soft-muted" aria-hidden="true" />
      <span className="truncate font-medium text-ink" title={current}>
        {current}
      </span>
    </nav>
  );
}

function MobileTabBar() {
  const { openAdd, openHelp } = useWorkspace();
  const pathname = usePathname();
  const itemClass = (active: boolean) =>
    cn(
      "flex flex-1 flex-col items-center gap-1 py-2 text-[11px] font-medium",
      active ? "text-primary" : "text-muted-foreground"
    );
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-paper/95 backdrop-blur md:hidden">
      <Link className={itemClass(pathname === "/")} href="/">
        <BookOpenText size={18} />
        Library
      </Link>
      <button type="button" className={itemClass(false)} onClick={openAdd}>
        <Plus size={18} />
        Add
      </button>
      <button type="button" className={itemClass(false)} onClick={openHelp}>
        <CircleHelp size={18} />
        Help
      </button>
    </nav>
  );
}
