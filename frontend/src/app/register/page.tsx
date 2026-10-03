"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { AuthFrame, AuthHeading, AuthMessage } from "@/components/AuthFrame";
import { authRequest } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await authRequest("register", { name, email, password });
      setDone(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create your account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <AuthHeading
        eyebrow="Get started"
        title="Create your account"
        description="Save your audio notes and access them from your workspace."
      />
      {/* Demo account (has seeded meetings): ksauravjet@gmail.com / Saurav9582840797 */}
      <p className="mb-4 rounded-md border border-dashed border-border bg-canvas p-2 text-xs text-muted-foreground">
        Demo account &mdash; <span className="font-medium">ksauravjet@gmail.com</span> /{" "}
        <span className="font-medium">Saurav9582840797</span>
      </p>
      {done ? (
        <AuthMessage tone="success">
          <strong>Account created.</strong>
          <p className="mt-1">
            Check your email for a verification link, then{" "}
            <Link href="/login" className="font-medium underline">
              log in
            </Link>
            .
          </p>
        </AuthMessage>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" autoComplete="name" maxLength={100} required value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email address</Label>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} />
            <p className="text-xs text-muted-foreground">Use at least 12 characters, with uppercase, lowercase, and a number.</p>
          </div>
          {error && <AuthMessage tone="error">{error}</AuthMessage>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Creating account…" : "Create account"}
          </Button>
        </form>
      )}
      <p className="mt-4 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Log in
        </Link>
      </p>
    </AuthFrame>
  );
}
