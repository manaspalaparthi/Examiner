import { NextResponse } from "next/server";
import { conversations } from "@/lib/mock-data";

// TODO: replace in-memory store with a real database and add auth.

interface Ctx {
  params: Promise<{ id: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { id } = await params;
  const c = conversations.find((x) => x.id === id);
  if (!c) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(c);
}
