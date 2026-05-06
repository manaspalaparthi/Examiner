import { PageHeader } from "@/components/shared/page-header";
import { CreateAgentForm } from "@/components/agents/create-agent-form";
import { voices } from "@/lib/mock-data";

export default function CreateAgentPage() {
  return (
    <>
      <PageHeader
        title="Create agent"
        description="Configure a new voice agent. You can refine the prompt and tools after it's created."
      />
      <CreateAgentForm voices={voices} />
    </>
  );
}
