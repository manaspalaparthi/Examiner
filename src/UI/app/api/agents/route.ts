import { NextResponse } from "next/server";
import { getUser } from "@/lib/supabase/server";
import { forward } from "@/lib/voice-api-forward";

export async function GET() {
  return forward("/api/agents", { cache: "no-store" });
}

export async function POST(req: Request) {
  const user = await getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const payload = await req.json();
  return forward("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      userId: payload.userId ?? user.id,
      status: payload.status ?? "active",
    }),
  });
}
