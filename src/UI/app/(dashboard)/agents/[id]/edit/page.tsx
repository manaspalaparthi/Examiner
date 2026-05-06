import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { CreateAgentForm } from "@/components/agents/create-agent-form";
import { Button } from "@/components/ui/button";
import { voices } from "@/lib/mock-data";
import { getAgent } from "@/lib/voice-api";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function EditAgentPage({ params }: Props) {
  const { id } = await params;
  const agent = await getAgent(id).catch(() => null);
  if (!agent) notFound();

  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2 text-[var(--muted-foreground)]">
        <Link href={`/agents/${agent.id}`}>
          <ArrowLeft /> Back to agent
        </Link>
      </Button>

      <PageHeader
        title={`Edit ${agent.name}`}
        description="Update the agent's behavior, model, voice, tools, and status."
      />
      <CreateAgentForm voices={voices} agent={agent} />
    </>
  );
}
