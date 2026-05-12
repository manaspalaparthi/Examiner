import { forward } from "@/lib/voice-api-forward";

interface Ctx {
  params: Promise<{ id: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { id } = await params;
  return forward(`/api/conversations/${encodeURIComponent(id)}`, { cache: "no-store" });
}
