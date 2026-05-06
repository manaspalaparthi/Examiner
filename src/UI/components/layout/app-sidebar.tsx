"use client";

import Link from "next/link";
import { Waves } from "lucide-react";
import { NAV_GROUPS, NAV_ITEMS } from "@/lib/nav";
import { NavItem } from "./nav-item";
import { UserProfile } from "./user-profile";

interface AppSidebarProps {
  onNavigate?: () => void;
}

export function AppSidebar({ onNavigate }: AppSidebarProps) {
  return (
    <aside className="flex h-full w-full flex-col border-r border-[var(--border)] bg-[var(--card)]">
      <div className="flex h-14 items-center gap-2 border-b border-[var(--border)] px-4">
        <Link href="/overview" onClick={onNavigate} className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-[var(--primary)] text-[var(--primary-foreground)]">
            <Waves className="size-4" strokeWidth={2} />
          </div>
          <span className="text-sm font-semibold tracking-tight">Voice AI</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => {
          const items = NAV_ITEMS.filter((i) => i.group === group.id);
          if (items.length === 0) return null;
          return (
            <div key={group.id} className="mb-4">
              {group.label && (
                <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                  {group.label}
                </div>
              )}
              <div className="flex flex-col gap-0.5">
                {items.map((item) => (
                  <NavItem
                    key={item.href}
                    href={item.href}
                    label={item.label}
                    icon={item.icon}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </nav>

      <div className="border-t border-[var(--border)] p-3">
        <UserProfile />
      </div>
    </aside>
  );
}
