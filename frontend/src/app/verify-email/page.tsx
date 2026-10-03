"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AuthFrame, AuthHeading, AuthMessage } from "@/components/AuthFrame";
import { authRequest } from "@/lib/auth";

export default function VerifyEmailPage() {
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("Checking your verification link…");
  const [error, setError] = useState("");

  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("token") || "";
    setToken(value);
    if (!value) {
      setMessage("");
      setError("This verification link is missing its token.");
      return;
    }
    void authRequest<{ message: string }>("verify-email", { token: value })
      .then((result) => setMessage(result.message))
      .catch((reason: unknown) => {
        setMessage("");
        setError(reason instanceof Error ? reason.message : "Could not verify this email.");
      });
  }, []);

  return (
    <AuthFrame>
      <AuthHeading
        eyebrow="Email verification"
        title="Verify your email"
        description="Confirm your email address to finish setting up your account."
      />
      {message && <AuthMessage tone="success">{message}</AuthMessage>}
      {error && <AuthMessage tone="error">{error}</AuthMessage>}
      {token && (
        <p className="mt-4 text-center text-sm text-muted-foreground">
          <Link href="/login" className="font-medium text-primary hover:underline">
            Continue to log in
          </Link>
        </p>
      )}
    </AuthFrame>
  );
}
