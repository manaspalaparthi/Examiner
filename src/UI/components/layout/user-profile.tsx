"use client";

import { ChevronsUpDown, CreditCard, UserCircle, Settings as SettingsIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ADMIN_USER } from "@/lib/auth";
import { SignOutItem } from "./sign-out-item";

export const MOCK_USER = {
  name: ADMIN_USER.name,
  email: ADMIN_USER.email,
  initials: ADMIN_USER.initials,
  workspace: ADMIN_USER.workspace,
};

export function UserProfile() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex w-full items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--background)] p-2 text-left transition-colors hover:bg-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
      >
        <Avatar className="h-8 w-8">
          <AvatarFallback className="bg-[var(--primary)] text-[var(--primary-foreground)]">{MOCK_USER.initials}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{MOCK_USER.name}</div>
          <div className="truncate text-xs text-[var(--muted-foreground)]">{MOCK_USER.workspace}</div>
        </div>
        <ChevronsUpDown className="size-4 text-[var(--muted-foreground)]" />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="end" className="w-56">
        <DropdownMenuLabel>
          <div className="text-sm font-medium text-[var(--foreground)]">{MOCK_USER.name}</div>
          <div className="text-xs text-[var(--muted-foreground)]">{MOCK_USER.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem>
          <UserCircle /> Account
        </DropdownMenuItem>
        <DropdownMenuItem>
          <CreditCard /> Billing
        </DropdownMenuItem>
        <DropdownMenuItem>
          <SettingsIcon /> Workspace settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <SignOutItem className="text-[var(--destructive)] focus:text-[var(--destructive)]" />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
