import type { LucideIcon } from "lucide-react";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string;
  icon: LucideIcon;
  delta?: { value: string; trend: "up" | "down" | "flat" };
  hint?: string;
}

export function StatCard({ label, value, icon: Icon, delta, hint }: StatCardProps) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="flex flex-col gap-3 p-5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
            {label}
          </span>
          <span className="flex size-8 items-center justify-center rounded-md bg-[var(--muted)] text-[var(--muted-foreground)]">
            <Icon className="size-4" strokeWidth={1.75} />
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-2xl font-semibold tracking-tight tabular-nums">{value}</span>
          {delta && (
            <span
              className={cn(
                "inline-flex items-center gap-0.5 text-xs font-medium",
                delta.trend === "up" && "text-[var(--success)]",
                delta.trend === "down" && "text-[var(--destructive)]",
                delta.trend === "flat" && "text-[var(--muted-foreground)]",
              )}
            >
              {delta.trend === "up" && <ArrowUpRight className="size-3.5" />}
              {delta.trend === "down" && <ArrowDownRight className="size-3.5" />}
              {delta.value}
            </span>
          )}
        </div>
        {hint && <p className="text-xs text-[var(--muted-foreground)]">{hint}</p>}
      </CardContent>
    </Card>
  );
}
