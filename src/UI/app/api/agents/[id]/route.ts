import { NextResponse } from "next/server";
import { voiceApiUrl } from "@/lib/voice-api";

interface Ctx {
  params: Promise<{ id: string }>;
}

async function forward(path: string, init?: RequestInit) {
  try {
    const res = await fetch(voiceApiUrl(path), init);
    const hasBody = ![204, 205, 304].includes(res.status);
    const body = hasBody ? await res.text() : null;
    const headers = new Headers();
    const contentType = res.headers.get("Content-Type");
    if (contentType && hasBody) {
      headers.set("Content-Type", contentType);
    }

    return new NextResponse(body, {
      status: res.status,
      headers,
    });
  } catch {
    return NextResponse.json(
      { error: "Voice API is unavailable" },
      { status: 502 },
    );
  }
}

export async function GET(_req: Request, { params }: Ctx) {
  const { id } = await params;
  return forward(`/api/agents/${encodeURIComponent(id)}`, { cache: "no-store" });
}

export async function PATCH(req: Request, { params }: Ctx) {
  const { id } = await params;
  return forward(`/api/agents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: await req.text(),
  });
}

export async function DELETE(_req: Request, { params }: Ctx) {
  const { id } = await params;
  return forward(`/api/agents/${encodeURIComponent(id)}`, { method: "DELETE" });
}
