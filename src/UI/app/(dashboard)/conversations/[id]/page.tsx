import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Bot, User } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { ConversationStatusBadge } from "@/components/shared/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { conversations } from "@/lib/mock-data";
import { formatDuration, formatRelativeTime, cn } from "@/lib/utils";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function ConversationDetailPage({ params }: Props) {
  const { id } = await params;
  const c = conversations.find((x) => x.id === id);
  if (!c) notFound();

  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2 text-[var(--muted-foreground)]">
        <Link href="/conversations">
          <ArrowLeft /> Back to conversations
        </Link>
      </Button>

      <PageHeader
        title={`Call with ${c.agentName}`}
        description={c.callerNumber}
        actions={<ConversationStatusBadge status={c.status} />}
      />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Transcript</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {c.messages.map((m) => (
              <div
                key={m.id}
                className={cn("flex items-start gap-3", m.role === "user" && "flex-row-reverse")}
              >
                <div
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full",
                    m.role === "agent"
                      ? "bg-[var(--muted)] text-[var(--muted-foreground)]"
                      : "bg-[var(--primary)] text-[var(--primary-foreground)]",
                  )}
                >
                  {m.role === "agent" ? <Bot className="size-4" /> : <User className="size-4" />}
                </div>
                <div
                  className={cn(
                    "max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
                    m.role === "agent"
                      ? "bg-[var(--muted)] text-[var(--foreground)]"
                      : "bg-[var(--primary)] text-[var(--primary-foreground)]",
                  )}
                >
                  {m.content}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="self-start">
          <CardHeader>
            <CardTitle className="text-sm">Details</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            <Row k="Conversation ID" v={<span className="font-mono text-xs">{c.id}</span>} />
            <Row k="Agent" v={c.agentName} />
            <Row k="Caller" v={<span className="font-mono text-xs">{c.callerNumber}</span>} />
            <Row k="Started" v={formatRelativeTime(c.startedAt)} />
            <Row k="Duration" v={c.durationSec ? formatDuration(c.durationSec) : "—"} />
            <Row k="Messages" v={c.messages.length} />
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] py-1.5 last:border-0">
      <span className="text-[var(--muted-foreground)]">{k}</span>
      <span>{v}</span>
    </div>
  );
}
