import { Phone, MessagesSquare, Users, Zap, Webhook, BarChart3 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { integrations } from "@/lib/mock-data";

const ICONS: Record<string, LucideIcon> = {
  phone: Phone,
  messages: MessagesSquare,
  users: Users,
  zap: Zap,
  webhook: Webhook,
  chart: BarChart3,
};

const CATEGORY_LABEL: Record<string, string> = {
  telephony: "Telephony",
  crm: "CRM",
  messaging: "Messaging",
  automation: "Automation",
  analytics: "Analytics",
};

export default function IntegrationsPage() {
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect your voice agents to the rest of your stack."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {integrations.map((i) => {
          const Icon = ICONS[i.iconKey] ?? Zap;
          return (
            <Card key={i.id}>
              <CardContent className="flex flex-col gap-4 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex size-10 items-center justify-center rounded-lg bg-[var(--muted)]">
                    <Icon className="size-5 text-[var(--muted-foreground)]" strokeWidth={1.75} />
                  </div>
                  {i.connected ? (
                    <Badge variant="success">Connected</Badge>
                  ) : (
                    <Badge variant="muted">Not connected</Badge>
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{i.name}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {CATEGORY_LABEL[i.category]}
                    </Badge>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-[var(--muted-foreground)]">{i.description}</p>
                </div>
                <Button variant={i.connected ? "outline" : "default"} className="w-full">
                  {i.connected ? "Manage" : "Connect"}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </>
  );
}
