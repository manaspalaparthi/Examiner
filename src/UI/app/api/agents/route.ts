import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { ADMIN_USER, AUTH_COOKIE, isValidSession } from "@/lib/auth";
import { voiceApiUrl } from "@/lib/voice-api";

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

export async function GET() {
  return forward("/api/agents", { cache: "no-store" });
}

export async function POST(req: Request) {
  const session = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!isValidSession(session)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const payload = await req.json();
  return forward("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      userId: payload.userId ?? ADMIN_USER.id,
      status: payload.status ?? "active",
    }),
  });
}
