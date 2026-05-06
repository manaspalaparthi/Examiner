import { NextResponse } from "next/server";
import { conversations } from "@/lib/mock-data";

// TODO: replace in-memory store with a real database and add auth.

export async function GET(req: Request) {
  const url = new URL(req.url);
  const agentId = url.searchParams.get("agentId");
  const status = url.searchParams.get("status");

  let rows = conversations;
  if (agentId) rows = rows.filter((c) => c.agentId === agentId);
  if (status) rows = rows.filter((c) => c.status === status);
  return NextResponse.json(rows);
}
