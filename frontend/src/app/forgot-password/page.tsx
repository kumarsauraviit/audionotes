"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { AuthFrame, AuthHeading, AuthMessage } from "@/components/AuthFrame";
import { authRequest } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await authRequest<{ message: string }>("forgot-password", { email });
      setMessage(result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not submit the request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <AuthHeading
        eyebrow="Account recovery"
        title="Reset your password"
        description="Enter your account email and we’ll send a reset link if an account matches."
      />
      {message ? (
        <AuthMessage tone="success">{message}</AuthMessage>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email address</Label>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          {error && <AuthMessage tone="error">{error}</AuthMessage>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
      <p className="mt-4 text-center text-sm text-muted-foreground">
        <Link href="/login" className="font-medium text-primary hover:underline">
          Back to log in
        </Link>
      </p>
    </AuthFrame>
  );
}
