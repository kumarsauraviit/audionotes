"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthFrame, AuthHeading, AuthMessage } from "@/components/AuthFrame";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const { login, isAuthenticated, isLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [redirectTo, setRedirectTo] = useState("/");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setRedirectTo(params.get("redirect") || "/");
  }, []);

  useEffect(() => {
    if (!isLoading && isAuthenticated) router.replace(redirectTo);
  }, [isAuthenticated, isLoading, redirectTo, router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      router.push(redirectTo);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invalid email or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <AuthHeading
        eyebrow="Welcome back"
        title="Log in to Audio Notes"
        description="Pick up where you left off and revisit your recordings."
      />
      {/* Demo account (has seeded meetings): ksauravjet@gmail.com / Saurav9582840797 */}
      <p className="mb-4 rounded-md border border-dashed border-border bg-canvas p-2 text-xs text-muted-foreground">
        Demo account &mdash; <span className="font-medium">ksauravjet@gmail.com</span> /{" "}
        <span className="font-medium">Saurav9582840797</span>
      </p>
      <form className="flex flex-col gap-3" onSubmit={submit}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email address</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            placeholder="name@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link href="/forgot-password" className="text-xs text-primary hover:underline">
              Forgot password?
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            placeholder="••••••••••••"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error && (
          <AuthMessage tone="error">
            <p>{error}</p>
            {error.toLowerCase().includes("verif") && (
              <p className="mt-1.5">
                <Link href="/verify-email" className="font-medium underline">
                  Go to email verification
                </Link>
              </p>
            )}
          </AuthMessage>
        )}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Logging in…" : "Log in"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted-foreground">
        New to Audio Notes?{" "}
        <Link href="/register" className="font-medium text-primary hover:underline">
          Create an account
        </Link>
      </p>
    </AuthFrame>
  );
}
