import {
  LayoutDashboard,
  Bot,
  PlusCircle,
  Sparkles,
  Mic2,
  MessagesSquare,
  BarChart3,
  Plug,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  group?: "main" | "build" | "data" | "configure";
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/overview", icon: LayoutDashboard, group: "main" },
  { label: "Agents", href: "/agents", icon: Bot, group: "build" },
  { label: "Create Agent", href: "/create-agent", icon: PlusCircle, group: "build" },
  { label: "Playground", href: "/playground", icon: Sparkles, group: "build" },
  { label: "Voice Settings", href: "/voice-settings", icon: Mic2, group: "build" },
  { label: "Conversations", href: "/conversations", icon: MessagesSquare, group: "data" },
  { label: "Analytics", href: "/analytics", icon: BarChart3, group: "data" },
  { label: "Integrations", href: "/integrations", icon: Plug, group: "configure" },
  { label: "Settings", href: "/settings", icon: Settings, group: "configure" },
];

export const NAV_GROUPS: { id: NonNullable<NavItem["group"]>; label: string }[] = [
  { id: "main", label: "" },
  { id: "build", label: "Build" },
  { id: "data", label: "Insights" },
  { id: "configure", label: "Configure" },
];
