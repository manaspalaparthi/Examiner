"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";

export function SignOutItem({ className }: { className?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <DropdownMenuItem
      className={className}
      disabled={pending}
      onSelect={(event) => {
        event.preventDefault();
        startTransition(() => {
          void fetch("/api/auth/logout", { method: "POST" }).finally(() => {
            router.replace("/login");
            router.refresh();
          });
        });
      }}
    >
      <LogOut /> Sign out
    </DropdownMenuItem>
  );
}
