"use client";
import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-[var(--card)] group-[.toaster]:text-[var(--card-foreground)] group-[.toaster]:border group-[.toaster]:border-[var(--border)] group-[.toaster]:shadow-lg group-[.toaster]:rounded-xl",
          description: "group-[.toast]:text-[var(--muted-foreground)]",
        },
      }}
    />
  );
}
