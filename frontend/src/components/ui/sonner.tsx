"use client";

import { Toaster as Sonner, type ToasterProps } from "sonner";

function Toaster(props: ToasterProps) {
  return (
    <Sonner
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: "rounded-md border border-border bg-card text-foreground shadow-lg",
          description: "text-muted-foreground",
          actionButton: "bg-primary text-primary-foreground",
          error: "border-destructive/30",
          success: "border-green/30",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
