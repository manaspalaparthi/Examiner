import { NextResponse } from "next/server";
import { voiceApiUrl } from "@/lib/voice-api";

interface Ctx {
  params: Promise<{ id: string }>;
}

export async function POST(req: Request, { params }: Ctx) {
  const { id } = await params;

  try {
    const res = await fetch(voiceApiUrl(`/api/agents/${encodeURIComponent(id)}/chat`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await req.text(),
    });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Voice API is unavailable" },
      { status: 502 },
    );
  }
}
