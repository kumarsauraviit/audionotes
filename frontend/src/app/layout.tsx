import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { AppProviders } from "@/components/AppProviders";
import { WorkspaceProvider } from "@/components/WorkspaceProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Audio Notes | Listen less, remember more",
  description: "Turn audio recordings into clear transcripts and useful notes.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="bg-canvas text-ink antialiased">
        <AuthProvider>
          <AppProviders>
            <WorkspaceProvider>{children}</WorkspaceProvider>
          </AppProviders>
        </AuthProvider>
      </body>
    </html>
  );
}
