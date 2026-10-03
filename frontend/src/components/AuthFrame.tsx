import type { ReactNode } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";

import { Brand } from "./Brand";

export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center bg-canvas px-5 py-6">
      <div className="flex w-full max-w-5xl items-center justify-between">
        <Brand />
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"
        >
          <ChevronLeft size={15} /> Back to library
        </Link>
      </div>
      <section className="mt-10 w-full max-w-md rounded-lg border border-border bg-card p-7 shadow-sm">
        {children}
      </section>
      <p className="mt-6 text-xs text-muted-foreground">Your recordings, transcripts, and notes in one place.</p>
    </main>
  );
}

export function AuthHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="mb-5 flex flex-col gap-1">
      <span className="text-xs font-semibold uppercase tracking-wide text-primary">{eyebrow}</span>
      <h1 className="m-0 text-xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm text-muted-foreground">{description}</p>
    </header>
  );
}

export function AuthMessage({ tone, children }: { tone: "error" | "success"; children: ReactNode }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={
        tone === "error"
          ? "rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
          : "rounded-md border border-green/30 bg-green/5 p-3 text-sm text-green"
      }
    >
      {children}
    </div>
  );
}
