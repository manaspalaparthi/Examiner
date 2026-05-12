import { NextResponse } from "next/server";
import { getUser } from "@/lib/supabase/server";
import { forward } from "@/lib/voice-api-forward";

interface Ctx {
  params: Promise<{ id: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { id } = await params;
  return forward(`/api/agents/${encodeURIComponent(id)}`, { cache: "no-store" });
}

export async function PATCH(req: Request, { params }: Ctx) {
  const user = await getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { id } = await params;
  return forward(`/api/agents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: await req.text(),
  });
}

export async function DELETE(_req: Request, { params }: Ctx) {
  const user = await getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { id } = await params;
  return forward(`/api/agents/${encodeURIComponent(id)}`, { method: "DELETE" });
}
