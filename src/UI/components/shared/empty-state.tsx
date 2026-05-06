import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[var(--border)] bg-[var(--card)] py-16 text-center",
        className,
      )}
    >
      <div className="flex size-10 items-center justify-center rounded-full bg-[var(--muted)] text-[var(--muted-foreground)]">
        <Icon className="size-5" strokeWidth={1.75} />
      </div>
      <div>
        <div className="text-sm font-medium">{title}</div>
        {description && <div className="mt-1 max-w-sm text-sm text-[var(--muted-foreground)]">{description}</div>}
      </div>
      {action}
    </div>
  );
}
