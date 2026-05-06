import Link from "next/link";
import { PlusCircle } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { AgentsTable } from "@/components/agents/agents-table";
import { listAgents } from "@/lib/voice-api";

export default async function AgentsPage() {
  const agents = await listAgents().catch(() => []);

  return (
    <>
      <PageHeader
        title="Agents"
        description="Build, configure, and deploy your voice agents."
        actions={
          <Button asChild>
            <Link href="/create-agent">
              <PlusCircle /> Create agent
            </Link>
          </Button>
        }
      />
      <AgentsTable agents={agents} />
    </>
  );
}
