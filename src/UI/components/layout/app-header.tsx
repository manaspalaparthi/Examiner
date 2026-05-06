"use client";

import { Bell, Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NAV_ITEMS } from "@/lib/nav";
import { MobileNav } from "./mobile-nav";
import { MOCK_USER } from "./user-profile";
import { SignOutItem } from "./sign-out-item";

function currentPageLabel(pathname: string): string {
  const match = NAV_ITEMS.find((n) => pathname === n.href || pathname.startsWith(n.href + "/"));
  return match?.label ?? "Dashboard";
}

export function AppHeader() {
  const pathname = usePathname();
  const label = currentPageLabel(pathname);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-[var(--border)] bg-[var(--background)]/80 px-4 backdrop-blur-md">
      <MobileNav />
      <div className="hidden items-center gap-2 lg:flex">
        <span className="text-xs text-[var(--muted-foreground)]">Dashboard</span>
        <span className="text-xs text-[var(--muted-foreground)]">/</span>
        <span className="text-sm font-medium">{label}</span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <div className="relative hidden md:block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input placeholder="Search agents, calls…" className="h-9 w-64 pl-8 pr-12" />
          <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 select-none items-center gap-1 rounded border border-[var(--border)] bg-[var(--muted)] px-1.5 font-mono text-[10px] font-medium text-[var(--muted-foreground)] sm:flex">
            ⌘K
          </kbd>
        </div>

        <Button variant="ghost" size="icon" aria-label="Notifications">
          <Bell />
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 rounded-full focus:outline-none focus:ring-2 focus:ring-[var(--ring)]">
            <Avatar className="h-8 w-8">
              <AvatarFallback className="bg-[var(--primary)] text-[var(--primary-foreground)]">
                {MOCK_USER.initials}
              </AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="text-sm font-medium">{MOCK_USER.name}</div>
              <div className="text-xs text-[var(--muted-foreground)]">{MOCK_USER.email}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>Profile</DropdownMenuItem>
            <DropdownMenuItem>Settings</DropdownMenuItem>
            <DropdownMenuSeparator />
            <SignOutItem />
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
