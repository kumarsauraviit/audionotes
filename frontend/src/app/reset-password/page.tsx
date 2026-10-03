"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

import { AuthFrame, AuthHeading, AuthMessage } from "@/components/AuthFrame";
import { authRequest } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") || "");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await authRequest<{ message: string }>("reset-password", { token, new_password: password });
      setMessage(result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reset your password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <AuthHeading
        eyebrow="Account recovery"
        title="Choose a new password"
        description="Set a new password for your Audio Notes account."
      />
      {message ? (
        <AuthMessage tone="success">
          {message}{" "}
          <Link href="/login" className="font-medium underline">
            Log in
          </Link>
          .
        </AuthMessage>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="token">Reset token</Label>
            <Input id="token" required value={token} onChange={(event) => setToken(event.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">New password</Label>
            <Input id="password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} />
            <p className="text-xs text-muted-foreground">Use at least 12 characters, with uppercase, lowercase, and a number.</p>
          </div>
          {error && <AuthMessage tone="error">{error}</AuthMessage>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Saving…" : "Reset password"}
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
